"""模块功能：确认侧边栏与二级菜单的到达状态。

上层调用：
- application.navigation：确认侧边栏、建造、强化三个页面是否到达或离开。

下层依赖：
- common.vision：读取模板事实。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sidebar'

# 本模块的模板文件名；目录小写、文件名全大写。
SIDEBAR_MAIN_TEMPLATE = 'SIDEBAR_MAIN_720P.png'
BUILD_SUBMENU_TEMPLATE = 'SIDEBAR_BUILD_720P.png'
INTENSIFY_SUBMENU_TEMPLATE = 'SIDEBAR_INTENSIFY_720P.png'


# ── 侧边栏识别区域 ──────────────────────────────────────────────────────────

# 侧边栏展开时「改造」条目的归一化区域，校准基准为 1280x720 截图。
SIDEBAR_MAIN_ROI = ROI(0.118, 0.4694, 0.2453, 0.5306)


# ── 二级菜单识别区域 ────────────────────────────────────────────────────────

# 点「建造」「改造」后右侧弹出的二级菜单首项区域，同一校准基准。
BUILD_SUBMENU_ROI = ROI(0.3024, 0.332, 0.475, 0.407)
INTENSIFY_SUBMENU_ROI = ROI(0.3024, 0.4612, 0.4719, 0.5375)


# 导航确认节奏：点条目后要走完展开动画，识别不到就重试。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_sidebar_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认侧边栏是否展开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望侧边栏收起时为真，默认期望它展开。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(SIDEBAR_MAIN_TEMPLATE),
        roi=SIDEBAR_MAIN_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_build_submenu(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认建造二级菜单是否弹出。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望二级菜单收起时为真，默认期望它弹出。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(BUILD_SUBMENU_TEMPLATE),
        roi=BUILD_SUBMENU_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_intensify_submenu(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认强化二级菜单是否弹出。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望二级菜单收起时为真，默认期望它弹出。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(INTENSIFY_SUBMENU_TEMPLATE),
        roi=INTENSIFY_SUBMENU_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = ['check_build_submenu', 'check_intensify_submenu', 'check_sidebar_page']
