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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.exercise import constants
from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import (
    RecognitionProfile,
    Template,
    expect_ocr,
    expect_template_center,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.controller.types import ShipType
    from autowsgr.common.vision import TextDetection
    from autowsgr.dispatch.context import ContextHandle


# 只读当前一帧，不等待目标出现。
_SINGLE_FRAME_ATTEMPTS = 1


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
        template=_load_template(constants.OVERLAY_CLOSE_TEMPLATE),
        roi=constants.OVERLAY_CLOSE_ROI,
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
        template=_load_template(constants.OVERLAY_REFRESH_TEMPLATE),
        roi=constants.OVERLAY_REFRESH_ROI,
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
        template=_load_template(constants.OVERLAY_CHALLENGE_TEMPLATE),
        roi=constants.OVERLAY_CHALLENGE_ROI,
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
        roi=constants.RIVAL_SHIP_TYPE_ROIS,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=_SINGLE_FRAME_ATTEMPTS,
    ).observation
    levels = expect_ocr(
        ctx,
        roi=constants.RIVAL_SHIP_LEVEL_ROIS,
        allowlist=constants.LEVEL_ALLOWLIST,
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
        for slot in range(1, constants.EXERCISE_RIVAL_SLOTS + 1)
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _read_ship_type(group: Sequence[TextDetection]) -> ShipType | None:
    """把一组 OCR 结果解析成舰种，只接受枚举内的完整名称。"""
    text = ''.join(detection.recognized_text for detection in group).strip()
    return constants.SHIP_TYPE_BY_NAME.get(text)


def _read_level(group: Sequence[TextDetection]) -> int | None:
    """把一组 OCR 结果解析成舰船等级，取数字部分。"""
    text = ''.join(detection.recognized_text for detection in group).strip()
    matched = constants.LEVEL_REGEX.search(text)
    if matched is None:
        return None
    return int(matched.group(1))


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(constants.TEMPLATE_NAMESPACE, filename)


__all__ = [
    'RivalShip',
    'read_overlay_challenge_center',
    'read_overlay_close_center',
    'read_overlay_refresh_center',
    'read_rival_ships',
]
