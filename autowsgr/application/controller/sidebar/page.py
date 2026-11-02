"""模块功能：在侧边栏内执行一级条目跳转与关闭。

上层调用：
- application.ui.navigation：执行侧边栏与子页面之间的页面边动作。

下层依赖：
- application.ui.controller.sidebar.main_page.constants：提供侧边栏点击落点。
- application.ui.navigation.types：提供页面名称。

边界：只点击一级条目与关闭侧边栏，不识别画面、不确认终态、不涉及子页面业务。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.sidebar.main_page import constants
from autowsgr.application.ui.navigation.types import PageName
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.sidebar')


# ── 侧边栏导航目标 ──────────────────────────────────────────────────────────


class SidebarTarget(enum.Enum):
    """侧边栏一级菜单支持的目标页面。"""

    BUILD = '建造'
    INTENSIFY = '强化'
    FRIEND = '好友'

    @property
    def page_name(self) -> PageName:
        """返回导航器使用的页面名称。

        Returns:
            本入口对应的页面名称。
        """
        return _TARGET_PAGES[self]


_TARGET_PAGES: dict[SidebarTarget, PageName] = {
    SidebarTarget.BUILD: PageName.BUILD,
    SidebarTarget.INTENSIFY: PageName.INTENSIFY,
    SidebarTarget.FRIEND: PageName.FRIEND,
}


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class SidebarPage:
    """侧边栏的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 导航 ────────────────────────────────────────────────────────────────

    def go_to(self, target: SidebarTarget) -> None:
        """点击一级条目，展开对应二级菜单或直接切到对应页面。

        Args:
            target: 侧边栏一级条目对应的目标页面。

        Raises:
            ValueError: 目标没有配置落点。
        """
        position = constants.NAV_POSITIONS.get(target.name.lower())
        if position is None:
            raise ValueError(f'侧边栏没有该目标的落点: {target!r}')
        _log.info('[UI] 侧边栏 → 进入目标：target={!r}，position={!r}', target.value, position)
        self._ctx.runtime.ctrl.click(*position)

    def go_to_submenu(self, target: SidebarTarget) -> None:
        """点击二级菜单首项，进入对应的子页面。

        一级条目展开二级菜单后，首项才是真正的入口；只负责点击，
        是否进入了子页面由导航器用该页面的 checker 确认。

        Args:
            target: 该二级菜单指向的目标页面，目前支持建造与强化。

        Raises:
            ValueError: 目标没有配置二级菜单落点。
        """
        position = constants.SUBMENU_POSITIONS.get(target.name.lower())
        if position is None:
            raise ValueError(f'侧边栏没有该目标的二级菜单落点: {target!r}')
        _log.info('[UI] 侧边栏 → 进入二级菜单：target={!r}，position={!r}', target.value, position)
        self._ctx.runtime.ctrl.click(*position)

    def go_back(self) -> None:
        """点击空白处收起侧边栏。"""
        _log.info('[UI] 侧边栏 → 收起：position={!r}', constants.CLICK_CLOSE)
        self._ctx.runtime.ctrl.click(*constants.CLICK_CLOSE)


__all__ = ['SidebarPage', 'SidebarTarget']
