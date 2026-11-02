"""模块功能：确认建造页各标签的激活状态。

上层调用：
- application.navigation：确认建造页是否到达，以及切换标签后是否落在目标标签。

下层依赖：
- common.vision：读取模板事实。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间：建造页从侧边栏进入，因此嵌在 sidebar 命名空间下。
TEMPLATE_NAMESPACE = 'controller/sidebar/build'

# 本模块的模板文件名；目录小写、文件名全大写。
# 建造页默认落在「建造」标签，因此用它作为页面身份。
BUILD_TAB_TEMPLATE = 'BUILD_TAB_720P.png'
DISMANTLE_TAB_TEMPLATE = 'BUILD_DISMANTLE_TAB_720P.png'


# ── 建造页面识别区域 ────────────────────────────────────────────────────────

# 建造页四个标签中已采样的两个；校准基准为 1280x720 截图。
BUILD_TAB_ROI = ROI(0.1485, 0.0167, 0.2188, 0.0792)
DISMANTLE_TAB_ROI = ROI(0.2782, 0.0153, 0.3469, 0.0806)


# 导航确认节奏：切换标签要走完切换动画，识别不到就重试。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_build_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在建造页的默认标签上。

    建造页默认落在「建造」标签，因此页面身份用它表达；前识别判到达，后识别判离开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望离开建造页时为真，默认期望它到达。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(BUILD_TAB_TEMPLATE),
        roi=BUILD_TAB_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_dismantle_tab(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认建造页是否切到了「解体」标签。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望该标签未激活时为真，默认期望它激活。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(DISMANTLE_TAB_TEMPLATE),
        roi=DISMANTLE_TAB_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = ['check_build_page', 'check_dismantle_tab']
