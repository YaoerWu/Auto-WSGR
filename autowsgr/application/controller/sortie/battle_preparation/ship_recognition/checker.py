"""模块功能：识别出征准备页六个槽位的舰队事实。

上层调用：
- application.fleet_select：读取六槽舰名的 OCR 原文、舰种、等级与血条状态。
- application.controller.sortie.battle_preparation.quick_maintenance：复用六槽血条状态。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.constants：识别区域与参考色。
- application.controller.sortie.battle_preparation.ship_recognition.models：识别事实模型。
- application.controller.types：舰种枚举。
- common.vision：OCR 与像素识别入口。

边界：只读页面事实，不比对舰名清单、不判断阵容是否合格、不点击、不上报识别错误。
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.constants import (
    BLOOD_BAR_PROBES,
    BLOOD_EMPTY,
    BLOOD_GREEN,
    BLOOD_NO_SHIP,
    BLOOD_RED_PREPARE,
    BLOOD_YELLOW,
    COUNTRY_SUFFIX_PATTERN,
    FLEET_SLOT_COUNT,
    LEVEL_DIGIT_TRANSLATION,
    LEVEL_MAX,
    LEVEL_MIN,
    SHIP_LEVEL_ROIS,
    SHIP_NAME_ROIS,
    SHIP_TYPE_ROIS,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    FleetRecognition,
)
from autowsgr.application.controller.types import ShipType
from autowsgr.common.vision import (
    Color,
    CompositePixelSignature,
    PixelRule,
    PixelSignature,
    RecognitionProfile,
    expect_ocr,
    expect_pixels,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.common.vision import TextDetection
    from autowsgr.dispatch.context import ContextHandle


# ── 血条状态 ────────────────────────────────────────────────────────────────


class ShipDamage(StrEnum):
    """出征准备页单个槽位的血条状态。"""

    NO_SHIP = 'no_ship'
    NORMAL = 'normal'
    MODERATE = 'moderate'
    SEVERE = 'severe'


# 参考色到槽位状态的映射，按判定顺序排列；组合签名命中第一个成立的候选就停。
_BLOOD_COLORS: tuple[tuple[ShipDamage, Color], ...] = (
    (ShipDamage.NORMAL, BLOOD_GREEN),
    (ShipDamage.NO_SHIP, BLOOD_NO_SHIP),
    (ShipDamage.MODERATE, BLOOD_YELLOW),
    (ShipDamage.SEVERE, BLOOD_RED_PREPARE),
    (ShipDamage.SEVERE, BLOOD_EMPTY),
)

# 每个槽位一条组合签名：同一探针位上命中任一候选色即成立，命中的候选名就是槽位状态。
# 槽位按物理位置从左到右编号 1-6。
_BLOOD_SIGNATURES = tuple(
    CompositePixelSignature(
        f'slot_{slot}',
        tuple(
            PixelSignature(state.value, (PixelRule(x, y, color),)) for state, color in _BLOOD_COLORS
        ),
    )
    for slot, (x, y) in enumerate(BLOOD_BAR_PROBES, start=1)
)


# ── 文字规则 ────────────────────────────────────────────────────────────────

# 舰种名到枚举值的反查表；枚举值是游戏里的中文舰种全称。
_SHIP_TYPE_BY_NAME = {member.value: member for member in ShipType}

# 舰种文字可能带国籍括号，例如「轻母(U国)」，匹配枚举前先剥掉。
_COUNTRY_SUFFIX_REGEX = re.compile(COUNTRY_SUFFIX_PATTERN)

# 等级文字的形态是「LV.110」；只认这个前缀，避免把星级或其它数字当成等级。
_LEVEL_REGEX = re.compile(r'[Ll][Vv]\.?\s*([0-9ILilOoDdSsBb]{1,6})')


# ── 识别入口 ────────────────────────────────────────────────────────────────


def read_ship_damage(ctx: ContextHandle) -> dict[int, ShipDamage | None]:
    """读取出征准备页六个槽位的血条状态。

    一次识别只截一帧：六个探针位在同一帧上各自命中一个候选色，槽位顺序与画面
    从左到右一致。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        槽位序号（按画面从左到右 1-6）到血条状态的映射；某槽采样色不在参考色范围内
        时为 None。
    """
    result = expect_pixels(ctx, signature=_BLOOD_SIGNATURES, attempts=1)
    return {
        slot: None if match.matched_signature is None else ShipDamage(match.matched_signature)
        for slot, match in enumerate(result.observation, start=1)
    }


def read_fleet_recognition(ctx: ContextHandle) -> FleetRecognition:
    """读取出征准备页六个槽位的舰队识别事实。

    一次调用读两帧：舰种、等级、舰名共十八个区域在同一帧上逐个识别，血条另读一帧。
    舰名只返回 OCR 原文，是否属于当前舰名清单由上层比对。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        六槽的舰名原文、占用状态、舰种与等级，均按槽位顺序排列；识别不到的字段为空。
    """
    # 1. 三个文字字段共用一帧：区域顺序是舰种六槽、等级六槽、舰名六槽。
    text_result = expect_ocr(
        ctx,
        roi=(*SHIP_TYPE_ROIS, *SHIP_LEVEL_ROIS, *SHIP_NAME_ROIS),
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=1,
    )
    groups = text_result.observation
    type_groups = groups[:FLEET_SLOT_COUNT]
    level_groups = groups[FLEET_SLOT_COUNT : FLEET_SLOT_COUNT * 2]
    name_groups = groups[FLEET_SLOT_COUNT * 2 :]

    # 2. 占用状态来自血条：采样到空槽色以外的任何状态都算槽位上有船。
    damage = read_ship_damage(ctx)
    occupied = tuple(
        damage[slot] is not ShipDamage.NO_SHIP for slot in range(1, FLEET_SLOT_COUNT + 1)
    )

    # 3. 空槽不采信舰名：战役页的空槽在舰名行位置写着「类型限定」这类占位提示，
    #    只有血条确认有船时才算真的读到舰名。
    return FleetRecognition(
        name_texts=tuple(
            _read_name(group) if is_occupied else None
            for group, is_occupied in zip(name_groups, occupied, strict=True)
        ),
        occupied=occupied,
        ship_types=tuple(_read_ship_type(group) for group in type_groups),
        ship_levels=tuple(_read_level(group) for group in level_groups),
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _read_name(group: Sequence[TextDetection]) -> str | None:
    """取一个区域的舰名 OCR 原文。"""
    for detection in group:
        text = detection.recognized_text.strip()
        if text:
            return text
    return None


def _read_ship_type(group: Sequence[TextDetection]) -> ShipType | None:
    """取一个区域的舰种枚举值；不在枚举内的文字视为未识别。"""
    for detection in group:
        text = _COUNTRY_SUFFIX_REGEX.sub('', detection.recognized_text).strip()
        ship_type = _SHIP_TYPE_BY_NAME.get(text)
        if ship_type is not None:
            return ship_type
    return None


def _read_level(group: Sequence[TextDetection]) -> int | None:
    """取一个区域的舰船等级；形态不符或超出合法区间时视为未识别。"""
    for detection in group:
        match = _LEVEL_REGEX.search(detection.recognized_text)
        if match is None:
            continue
        normalized = ''.join(LEVEL_DIGIT_TRANSLATION.get(char, char) for char in match.group(1))
        if not normalized.isdigit():
            continue
        level = int(normalized)
        if LEVEL_MIN <= level <= LEVEL_MAX:
            return level
    return None


__all__ = [
    'ShipDamage',
    'read_fleet_recognition',
    'read_ship_damage',
]
