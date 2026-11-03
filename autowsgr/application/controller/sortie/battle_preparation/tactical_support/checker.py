"""模块功能：识别战术支援按钮的开启状态与浮窗内容。

上层调用：
- 战术支援业务编排：判断按钮是否已经开启，读取浮窗里的开关状态与今日剩余次数。

下层依赖：
- application.controller.sortie.battle_preparation.tactical_support.constants：识别区域与模板名。
- application.controller.template：加载本模块模板。
- common.vision：模板与 OCR 识别入口。

边界：只读页面事实，不点击、不判断这次该开还是该关、不关闭浮窗。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from autowsgr.application.controller.sortie.battle_preparation.tactical_support import constants
from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import expect_ocr, expect_template_center


if TYPE_CHECKING:
    from autowsgr.common.vision import Template, TextDetection
    from autowsgr.dispatch.context import ContextHandle


# ── 响应窗口 ────────────────────────────────────────────────────────────────

# 按钮开关要等一次重绘：重试 3 次、间隔 0.5 秒。
_BUTTON_ATTEMPTS = 3
_BUTTON_INTERVAL_SECONDS = 0.5

# 点开按钮后要等浮窗滑入，给足 5 次。
_POPUP_ATTEMPTS = 5
_POPUP_INTERVAL_SECONDS = 0.5


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 开关按钮的两种文案；浮窗在时必居其一。

# ── 识别模型 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TacticalSupportState:
    """战术支援浮窗读出的状态。"""

    enabled: bool
    remaining: int | None
    total: int | None
    toggle_center: tuple[float, float] | None


# ── 识别入口 ────────────────────────────────────────────────────────────────


def read_tactical_support_button_center(
    ctx: ContextHandle,
    *,
    attempts: int = _BUTTON_ATTEMPTS,
    interval_seconds: float = _BUTTON_INTERVAL_SECONDS,
) -> tuple[float, float] | None:
    """读战术支援按钮的中心，同时判定它是否处于已开启态。

    只匹配已开启态的橙底模板：返回非 None 说明按钮已经点亮；返回 None 说明按钮没点亮，
    也可能是这个页面根本没有这个按钮（决战准备页、战役准备页、演习准备页）。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        按钮模板的归一化中心；未开启或页面上没有这个按钮时为 None。
    """
    return expect_template_center(
        ctx,
        template=_load_template(constants.TACTICAL_SUPPORT_ACTIVE_TEMPLATE),
        roi=constants.TACTICAL_SUPPORT_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )


def read_tactical_support(
    ctx: ContextHandle,
    *,
    attempts: int = _POPUP_ATTEMPTS,
    interval_seconds: float = _POPUP_INTERVAL_SECONDS,
) -> TacticalSupportState | None:
    """读战术支援浮窗的开关状态与今日剩余次数。

    一次截图里分别识别开关按钮与剩余次数两个区域。浮窗不在时两个区域都读不到开关文案，
    直接返回 None，调用方据此判断浮窗没有打开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数，默认给足浮窗滑入的动画窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        浮窗状态；浮窗不在时为 None。
    """
    result = expect_ocr(
        ctx,
        roi=(constants.TACTICAL_SUPPORT_TOGGLE_ROI, constants.TACTICAL_SUPPORT_COUNT_ROI),
        expect=constants.TOGGLE_TEXTS,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if not result.satisfied or result.screenshot is None:
        return None
    # 传的是区域序列，因此每个区域一组检测结果。
    toggle_texts, count_texts = cast('list[list[TextDetection]]', result.observation)
    enabled = any(
        detection.recognized_text == constants.TOGGLE_TEXTS[1] for detection in toggle_texts
    )
    remaining, total = _parse_remaining(count_texts)
    # 检测框是相对识别区域的坐标，加上区域偏移才是整帧位置。
    height, width = result.screenshot.shape[:2]
    left, top, _right, _bottom = constants.TACTICAL_SUPPORT_TOGGLE_ROI.to_absolute(width, height)
    toggle_center: tuple[float, float] | None = None
    for detection in toggle_texts:
        region = detection.text_region
        if detection.recognized_text not in constants.TOGGLE_TEXTS or region is None:
            continue
        x1, y1, x2, y2 = region
        toggle_center = ((left + (x1 + x2) / 2) / width, (top + (y1 + y2) / 2) / height)
        break
    return TacticalSupportState(
        enabled=enabled,
        remaining=remaining,
        total=total,
        toggle_center=toggle_center,
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _parse_remaining(count_texts: list[TextDetection]) -> tuple[int | None, int | None]:
    """从剩余次数区读出「已用 / 总数」；识别不到时两项都返回 None。"""
    for detection in count_texts:
        found = constants.COUNT_PATTERN.search(detection.recognized_text)
        if found:
            return int(found.group('remaining')), int(found.group('total'))
    return None, None


def _load_template(filename: str) -> Template:
    """加载本模块模板；模板按参数缓存，重复调用不读盘。"""
    return load_ui_template(constants.TEMPLATE_NAMESPACE, filename)


__all__ = [
    'TacticalSupportState',
    'read_tactical_support',
    'read_tactical_support_button_center',
]
