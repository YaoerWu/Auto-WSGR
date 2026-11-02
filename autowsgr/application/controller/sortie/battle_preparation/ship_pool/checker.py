"""模块功能：识别船池页面的页面事实。

上层调用：
- application.fleet_select.ship_pool：读取船池列表上的文字与位置，据此决定点哪张卡。

下层依赖：
- application.controller.sortie.battle_preparation.ship_pool.constants：识别区域与页面签名。
- common.vision：OCR 与像素识别入口。

边界：只读页面事实，不比对舰名清单、不判断这张卡是不是目标船、不点击。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_pool.constants import (
    SEARCH_INPUT_SIGNATURE,
    SHIP_LIST_ROI,
    SHIP_POOL_SIGNATURE,
)
from autowsgr.common.vision import RecognitionProfile, expect_ocr, expect_pixels


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 页面返回值 ──────────────────────────────────────────────────────────────

# 进入或离开船池页面的等待窗口：页面切换有转场动画，给足 5 秒。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class ShipListText:
    """船池列表上的一段文字及其归一化中心。"""

    text: str
    center: tuple[float, float]


# ── 识别入口 ────────────────────────────────────────────────────────────────


def check_ship_pool_page(
    ctx: ContextHandle,
    *,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
    absent: bool = False,
) -> bool:
    """判断当前画面是不是船池页面。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。
        absent: 期望船池页面已经离开时为真。

    Returns:
        页面签名成立（或按 absent 期望消失）时为 True。
    """
    return expect_pixels(
        ctx,
        signature=SHIP_POOL_SIGNATURE,
        attempts=attempts,
        interval_seconds=interval_seconds,
        absent=absent,
    ).satisfied


def check_search_input(
    ctx: ContextHandle,
    *,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """判断船池页面的搜索输入框是否已经唤起软键盘。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        输入态签名成立时为 True。
    """
    return expect_pixels(
        ctx,
        signature=SEARCH_INPUT_SIGNATURE,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def read_ship_list_texts(ctx: ContextHandle) -> tuple[ShipListText, ...]:
    """读取船池列表区域上的全部文字及其归一化中心。

    一次识别只截一帧。文字原样返回，是否属于舰名清单由上层比对；没有检测框的结果
    无法换算位置，直接丢弃。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按画面阅读顺序排列的文字与中心列表。
    """
    result = expect_ocr(
        ctx,
        roi=SHIP_LIST_ROI,
        recognition_profile=RecognitionProfile.FULL,
        attempts=1,
    )
    frame = result.screenshot
    if frame is None:
        return ()

    height, width = frame.shape[:2]
    left, top, _, _ = SHIP_LIST_ROI.to_absolute(width, height)
    texts: list[ShipListText] = []
    for detection in result.observation:
        text = detection.recognized_text.strip()
        region = detection.text_region
        if not text or region is None:
            continue
        # text_region 是相对裁切图的 (x1, y1, x2, y2)，换回整帧坐标再加 ROI 偏移。
        region_x1, region_y1, region_x2, region_y2 = region
        texts.append(
            ShipListText(
                text=text,
                center=(
                    (left + (region_x1 + region_x2) / 2) / width,
                    (top + (region_y1 + region_y2) / 2) / height,
                ),
            )
        )
    return tuple(texts)


__all__ = [
    'ShipListText',
    'check_search_input',
    'check_ship_pool_page',
    'read_ship_list_texts',
]
