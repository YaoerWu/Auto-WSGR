"""模块功能：提供浴室二级页的页面控制器。

上层调用：
- application.ui.navigation：执行该页的页面边动作。

下层依赖：
- application.ui.controller.backyard.main_page.constants：提供三级页入口落点。

边界：只做本页特有的点击；退回上一级与回首页是二级页公共动作，
统一由 `backyard.main_page.page.BackyardPage` 提供，本模块不重复实现。
浴室的修理业务尚未迁移到新链路，等第二阶段移植后再补回本模块。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.backyard.main_page import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.backyard.bath_page')


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class BathPage:
    """浴室二级页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx
