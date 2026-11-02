"""模块功能：识别演习对手浮窗，并读取浮窗按钮的点击中心。

上层调用：
- application.navigation：读取关闭、刷新、挑战三个按钮的落点。

下层依赖：
- application.ui.template：加载本模块模板。
- common.vision：读取模板命中事实与模板中心。

边界：只做识别并返回结论，不执行点击、不等待页面、不判断对手是否已挑战。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template_center


if TYPE_CHECKING:
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


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 演习页ROI_720P.yaml 的 roi_px 换算，区域比模板各边大 1px。
OVERLAY_CLOSE_ROI = ROI(0.9, 0.2306, 0.9321, 0.2778)
OVERLAY_REFRESH_ROI = ROI(0.6485, 0.707, 0.7727, 0.7681)
OVERLAY_CHALLENGE_ROI = ROI(0.7891, 0.7098, 0.9149, 0.7695)


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


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'OVERLAY_CHALLENGE_ROI',
    'OVERLAY_CHALLENGE_TEMPLATE',
    'OVERLAY_CLOSE_ROI',
    'OVERLAY_CLOSE_TEMPLATE',
    'OVERLAY_REFRESH_ROI',
    'OVERLAY_REFRESH_TEMPLATE',
    'TEMPLATE_NAMESPACE',
    'read_overlay_challenge_center',
    'read_overlay_close_center',
    'read_overlay_refresh_center',
]
