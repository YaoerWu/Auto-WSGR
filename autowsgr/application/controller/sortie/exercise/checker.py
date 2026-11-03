"""模块功能：识别演习对手浮窗，并读取浮窗按钮的点击中心。

上层调用：
- application.navigation：读取关闭、刷新、挑战三个按钮的落点。
- application.fleet_select：读取浮窗上六个对手的舰种与等级。

下层依赖：
- application.controller.template：加载本模块模板。
- application.controller.types：舰种枚举。
- common.vision：读取模板命中事实、模板中心与 OCR 文本。

边界：只做识别并返回结论，不执行点击、不等待页面、不判断对手是否已挑战。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.controller.template import load_ui_template
from autowsgr.application.controller.types import ShipType
from autowsgr.common.vision import (
    ROI,
    RecognitionProfile,
    Template,
    expect_ocr,
    expect_template_center,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.common.vision import TextDetection
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/exercise'

# 三个按钮只用来定位点击中心，不作浮窗判据：关闭按钮在登录更新弹窗上也能命中
# 0.95，挑战按钮在无浮窗演习页上能命中 0.78。浮窗判据是标题模板，由
# sortie.checker 持有，好让浮窗和标签在一帧里判层叠关系。
OVERLAY_CLOSE_TEMPLATE = 'EXERCISE_OVERLAY_CLOSE_720P.png'
OVERLAY_REFRESH_TEMPLATE = 'EXERCISE_OVERLAY_REFRESH_720P.png'
OVERLAY_CHALLENGE_TEMPLATE = 'EXERCISE_OVERLAY_CHALLENGE_720P.png'

# 浮窗固定展示六个对手，槽位号即序列下标加一。
EXERCISE_RIVAL_SLOTS = 6

# 等级文字形如 LV.110，白名单只留 LV 字母、数字与小数点，避免其它符号噪声混入。
_LEVEL_ALLOWLIST = 'LV0123456789.'

# 只读当前一帧，不等待目标出现。
_SINGLE_FRAME_ATTEMPTS = 1

# 舰种名到枚举值的反查表；枚举值是游戏里的中文舰种全称。
_SHIP_TYPE_BY_NAME = {member.value: member for member in ShipType if member is not ShipType.Other}

# 等级文字取第一段数字，浮窗该区域只框住「LV.110」，没有星级干扰。
_LEVEL_REGEX = re.compile(r'(\d+)')


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 演习页ROI_720P.yaml 的 roi_px 换算，区域比模板各边大 1px。
OVERLAY_CLOSE_ROI = ROI(0.9, 0.2306, 0.9321, 0.2778)
OVERLAY_REFRESH_ROI = ROI(0.6485, 0.707, 0.7727, 0.7681)
OVERLAY_CHALLENGE_ROI = ROI(0.7891, 0.7098, 0.9149, 0.7695)

# 六个槽位的舰种文字区，从左到右；不含国籍括号，校准基准 1280x720。
RIVAL_SHIP_TYPE_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.5750, 0.3250, 0.6084),
    ROI(0.3945, 0.5750, 0.4321, 0.6084),
    ROI(0.5023, 0.5750, 0.5399, 0.6084),
    ROI(0.6093, 0.5750, 0.6469, 0.6084),
    ROI(0.7171, 0.5750, 0.7547, 0.6084),
    ROI(0.8250, 0.5750, 0.8625, 0.6084),
)

# 六个槽位的等级文字区，上边界紧接舰种区；不含星级，校准基准 1280x720。
RIVAL_SHIP_LEVEL_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.6084, 0.3297, 0.6320),
    ROI(0.3945, 0.6084, 0.4368, 0.6320),
    ROI(0.5023, 0.6084, 0.5446, 0.6320),
    ROI(0.6093, 0.6084, 0.6516, 0.6320),
    ROI(0.7171, 0.6084, 0.7594, 0.6320),
    ROI(0.8250, 0.6084, 0.8672, 0.6320),
)


# ── 识别事实 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RivalShip:
    """演习对手浮窗上单个槽位的识别事实。

    Attributes:
        slot: 槽位号，按浮窗从左到右从 1 开始。
        ship_type: 舰种；文字不在枚举内时为空。
        level: 舰船等级；识别失败时为空。
    """

    slot: int
    ship_type: ShipType | None = None
    level: int | None = None


# ── 按钮中心 ────────────────────────────────────────────────────────────────


def read_overlay_close_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取浮窗关闭按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        关闭按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(OVERLAY_CLOSE_TEMPLATE),
        roi=OVERLAY_CLOSE_ROI,
        attempts=1,
    )


def read_overlay_refresh_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取浮窗刷新按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        刷新按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(OVERLAY_REFRESH_TEMPLATE),
        roi=OVERLAY_REFRESH_ROI,
        attempts=1,
    )


def read_overlay_challenge_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取浮窗挑战按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        挑战按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(OVERLAY_CHALLENGE_TEMPLATE),
        roi=OVERLAY_CHALLENGE_ROI,
        attempts=1,
    )


def read_rival_ships(ctx: ContextHandle) -> tuple[RivalShip, ...]:
    """读取演习对手浮窗上六个槽位的舰种与等级。

    两次识别各截一帧：舰种六个区域一帧，等级六个区域一帧；返回顺序与浮窗从左到右
    一致。浮窗上不展示对手舰名，本入口只读舰种与等级。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按槽位号升序排列的六项事实；识别失败的字段为空。
    """
    ship_types = expect_ocr(
        ctx,
        roi=RIVAL_SHIP_TYPE_ROIS,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=_SINGLE_FRAME_ATTEMPTS,
    ).observation
    levels = expect_ocr(
        ctx,
        roi=RIVAL_SHIP_LEVEL_ROIS,
        allowlist=_LEVEL_ALLOWLIST,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=_SINGLE_FRAME_ATTEMPTS,
    ).observation
    # 传 roi 序列时同一帧内逐区域识别，observation 按区域分组、顺序同 roi。
    return tuple(
        RivalShip(
            slot=slot,
            ship_type=_read_ship_type(ship_types[slot - 1]),
            level=_read_level(levels[slot - 1]),
        )
        for slot in range(1, EXERCISE_RIVAL_SLOTS + 1)
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _read_ship_type(group: Sequence[TextDetection]) -> ShipType | None:
    """把一组 OCR 结果解析成舰种，只接受枚举内的完整名称。"""
    text = ''.join(detection.recognized_text for detection in group).strip()
    return _SHIP_TYPE_BY_NAME.get(text)


def _read_level(group: Sequence[TextDetection]) -> int | None:
    """把一组 OCR 结果解析成舰船等级，取数字部分。"""
    text = ''.join(detection.recognized_text for detection in group).strip()
    matched = _LEVEL_REGEX.search(text)
    if matched is None:
        return None
    return int(matched.group(1))


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'EXERCISE_RIVAL_SLOTS',
    'OVERLAY_CHALLENGE_ROI',
    'OVERLAY_CHALLENGE_TEMPLATE',
    'OVERLAY_CLOSE_ROI',
    'OVERLAY_CLOSE_TEMPLATE',
    'OVERLAY_REFRESH_ROI',
    'OVERLAY_REFRESH_TEMPLATE',
    'RIVAL_SHIP_LEVEL_ROIS',
    'RIVAL_SHIP_TYPE_ROIS',
    'TEMPLATE_NAMESPACE',
    'RivalShip',
    'read_overlay_challenge_center',
    'read_overlay_close_center',
    'read_overlay_refresh_center',
    'read_rival_ships',
]
