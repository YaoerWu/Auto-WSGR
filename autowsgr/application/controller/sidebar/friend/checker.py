"""模块功能：确认好友页面的到达状态。

上层调用：
- application.navigation：确认好友页面是否到达或离开。

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

# 本模块在 UI 模板根下的命名空间：好友从侧边栏进入，因此嵌在 sidebar 命名空间下。
TEMPLATE_NAMESPACE = 'controller/sidebar/friend'

# 本模块的模板文件名；目录小写、文件名全大写。
# 好友页面有两个页签，账号设置不同进入后停留的页签也不同，两个都要认。
FRIEND_TAB_TEMPLATE = 'FRIEND_TAB_720P.png'
FRIEND_ADD_TAB_TEMPLATE = 'FRIEND_ADD_TAB_720P.png'


# ── 好友页面识别区域 ────────────────────────────────────────────────────────

# 两个页签各自的归一化区域，校准基准为 1280x720 截图。
# 尺寸都比对应模板大 1px 以上，避免换算截断后区域小于模板。
# 「好友」页签（模板 86x46，区域 88x48）。
FRIEND_TAB_ROI = ROI(0.1484, 0.0139, 0.2172, 0.0806)
# 「添加」页签（模板 94x42，区域 96x44）。
FRIEND_ADD_TAB_ROI = ROI(0.4016, 0.0194, 0.4766, 0.0806)


# 导航确认节奏：从侧边栏切页要走完转场动画，识别不到就重试。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_friend_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认好友页面是否在前台。

    两个页签同属好友页：任一可见即算在好友页。前识别判到达，后识别判离开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望好友页面离开时为真，默认期望它出现。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=(
            _load_template(FRIEND_TAB_TEMPLATE),
            _load_template(FRIEND_ADD_TAB_TEMPLATE),
        ),
        roi=(FRIEND_TAB_ROI, FRIEND_ADD_TAB_ROI),
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = ['check_friend_page']
