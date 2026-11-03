"""模块功能：识别出征准备页六个槽位的舰队事实。

上层调用：
- application.fleet_select：分别读取六槽的血条状态、舰种文字、等级文字与舰名文字。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.constants：识别区域与血条签名。
- common.vision：OCR 与像素识别入口。

边界：只读页面事实并返回识别原文，不比对舰名清单、不解析等级、不判断阵容是否合格、
不点击、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import constants
from autowsgr.common.vision import RecognitionProfile, expect_ocr, expect_pixels


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.common.vision import ROI
    from autowsgr.dispatch.context import ContextHandle


def read_ship_damage(ctx: ContextHandle) -> list[constants.ShipDamage | None]:
    """读取出征准备页六个槽位的血条状态。

    一次识别只截一帧：六个探针位在同一帧上各自命中一个候选色。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        长度为六的槽位状态列表，下标 0 是画面最左侧槽位；采样色不在参考色范围内时
        为 None。
    """
    result = expect_pixels(ctx, signature=constants.BLOOD_SIGNATURES, attempts=1)
    return [
        None if match.matched_signature is None else constants.ShipDamage(match.matched_signature)
        for match in result.observation
    ]


def read_ship_types(ctx: ContextHandle) -> list[str | None]:
    """读取出征准备页六个槽位的舰种文字。

    返回 OCR 原文，不剥国籍括号、不匹配舰种枚举。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        长度为六的舰种文字列表，下标 0 是画面最左侧槽位；没有读出文字时为 None。
    """
    return _read_text_slots(ctx, constants.SHIP_TYPE_ROIS)


def read_ship_levels(ctx: ContextHandle) -> list[str | None]:
    """读取出征准备页六个槽位的等级文字。

    返回 OCR 原文，不解析等级数字、不校验合法区间。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        长度为六的等级文字列表，下标 0 是画面最左侧槽位；没有读出文字时为 None。
    """
    return _read_text_slots(ctx, constants.SHIP_LEVEL_ROIS)


def read_ship_names(ctx: ContextHandle) -> list[str | None]:
    """读取出征准备页六个槽位的舰名文字。

    返回 OCR 原文，不比对任何舰名清单，空槽上的占位提示也原样返回。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        长度为六的舰名文字列表，下标 0 是画面最左侧槽位；没有读出文字时为 None。
    """
    return _read_text_slots(ctx, constants.SHIP_NAME_ROIS)


def _read_text_slots(ctx: ContextHandle, rois: Sequence[ROI]) -> list[str | None]:
    """读取一帧里六个文字区域的首条非空识别文本。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        rois: 与六个槽位一一对应的文字识别区域。

    Returns:
        长度为六的识别原文列表，下标 0 是画面最左侧槽位；区域没有读出文字时为 None。
    """
    result = expect_ocr(
        ctx,
        roi=rois,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=1,
    )
    return [
        next((item.recognized_text for item in group if item.recognized_text.strip()), None)
        for group in result.observation
    ]


__all__ = [
    'read_ship_damage',
    'read_ship_levels',
    'read_ship_names',
    'read_ship_types',
]
