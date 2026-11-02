"""模块功能：确认餐厅二级页的到达状态。

上层调用：
- application.ui.navigation：确认餐厅二级页是否到达或离开。

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

# UI 模板根下的命名空间：二级页模板放在以页面命名的子目录里。
TEMPLATE_NAMESPACE = 'navigation/checker/backyard/canteen'

# 模板文件名；目录与命名空间已表达域，文件名不再重复域前缀。
PAGE_TEMPLATE = 'CANTEEN_PAGE_720P.png'

# 餐厅二级页页面身份的归一化区域，校准基准为 1280x720 截图。
PAGE_ROI = ROI(0.879, 0.1375, 0.9672, 0.1917)


# 导航确认节奏：页面切换要走完转场，识别不到就重试。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_canteen_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在餐厅二级页。

    前识别判到达，后识别判离开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望离开该页时为真，默认期望它到达。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(PAGE_TEMPLATE),
        roi=PAGE_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = ['check_canteen_page']
