"""模块功能：识别演习对手浮窗上的六个槽位。

上层调用：
- application.controller.sortie.battle_preparation.ship_recognition.service：按任务类型取演习对手的舰种与等级。

下层依赖：
- common.vision：同一帧内按多个区域读取 OCR 文本。
- application.controller.sortie.battle_preparation.ship_recognition.models：返回槽位事实。
- application.controller.types：识别舰种枚举。

边界：只读取浮窗文字并解析成事实，不点击、不刷新对手、不判断阵容是否合格。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    ShipInfo,
)
from autowsgr.application.controller.types import ShipType
from autowsgr.common.vision import ROI, RecognitionProfile, expect_ocr


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.common.vision import TextDetection
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 演习浮窗固定展示六个对手，槽位号即序列下标加一。
EXERCISE_RIVAL_SLOTS = 6

# 等级文字形如 LV.110，白名单只留 LV 字母、数字与小数点，避免其它符号噪声混入。
_LEVEL_ALLOWLIST = 'LV0123456789.'

# 只读当前一帧，不等待目标出现。
_SINGLE_FRAME_ATTEMPTS = 1


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 六个槽位的舰种文字区，从左到右；不含国籍括号，校准基准 1280x720。
_SHIP_TYPE_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.5750, 0.3250, 0.6084),
    ROI(0.3945, 0.5750, 0.4321, 0.6084),
    ROI(0.5023, 0.5750, 0.5399, 0.6084),
    ROI(0.6093, 0.5750, 0.6469, 0.6084),
    ROI(0.7171, 0.5750, 0.7547, 0.6084),
    ROI(0.8250, 0.5750, 0.8625, 0.6084),
)

# 六个槽位的等级文字区，上边界紧接舰种区；不含星级，校准基准 1280x720。
_SHIP_LEVEL_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.6084, 0.3297, 0.6320),
    ROI(0.3945, 0.6084, 0.4368, 0.6320),
    ROI(0.5023, 0.6084, 0.5446, 0.6320),
    ROI(0.6093, 0.6084, 0.6516, 0.6320),
    ROI(0.7171, 0.6084, 0.7594, 0.6320),
    ROI(0.8250, 0.6084, 0.8672, 0.6320),
)


# ── 识别入口 ────────────────────────────────────────────────────────────────


def recognize_rivals(ctx: ContextHandle) -> tuple[ShipInfo, ...]:
    """识别演习对手浮窗上的六个槽位。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按槽位号升序排列的六项事实；识别失败的字段为空。
    """
    ship_types = expect_ocr(
        ctx,
        roi=_SHIP_TYPE_ROIS,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=_SINGLE_FRAME_ATTEMPTS,
    ).observation
    levels = expect_ocr(
        ctx,
        roi=_SHIP_LEVEL_ROIS,
        allowlist=_LEVEL_ALLOWLIST,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=_SINGLE_FRAME_ATTEMPTS,
    ).observation
    # 传 roi 序列时同一帧内逐区域识别，observation 按区域分组、顺序同 roi。
    return tuple(
        ShipInfo(
            slot=slot,
            ship_type=_parse_ship_type(ship_types[slot - 1]),
            level=_parse_level(levels[slot - 1]),
        )
        for slot in range(1, EXERCISE_RIVAL_SLOTS + 1)
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _parse_ship_type(detections: Sequence[TextDetection]) -> ShipType | None:
    """把一组 OCR 结果解析成舰种，只接受枚举内的完整名称。"""
    text = ''.join(detection.recognized_text for detection in detections).strip()
    for ship_type in ShipType:
        if ship_type is not ShipType.Other and text == ship_type.value:
            return ship_type
    return None


def _parse_level(detections: Sequence[TextDetection]) -> int | None:
    """把一组 OCR 结果解析成舰船等级，取数字部分。"""
    text = ''.join(detection.recognized_text for detection in detections).strip()
    matched = re.search(r'(\d+)', text)
    if matched is None:
        return None
    return int(matched.group(1))
