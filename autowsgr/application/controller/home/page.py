"""模块功能：控制主页面的单次点击。

上层调用：
- application.ui.navigation：主页面的目标页导航与每日浮窗按钮点击。

下层依赖：
- main_page.constants：提供导航落点与浮窗点击落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不编排流程、不重试。
浮窗处理流程与页面确认由导航器负责；勾选框、领取、确认三个按钮的落点由调用方传入
识别产出的中心坐标。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.home.main_page import constants
from autowsgr.application.ui.navigation.types import PageName
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.home.main_page')


# ── 主页导航目标 ────────────────────────────────────────────────────────────────────


class Target(enum.Enum):
    """主页导航契约支持的目标页面。"""

    SORTIE = '出征'
    TASK = '任务'
    SIDEBAR = '侧边栏'
    BACKYARD = '后院'
    EVENT = '活动'

    @property
    def page_name(self) -> PageName:
        """返回导航器使用的页面名称。

        Returns:
            本入口对应的页面名称。
        """
        return _TARGET_PAGES[self]


_TARGET_PAGES: dict[Target, PageName] = {
    Target.SORTIE: PageName.SORTIE_MAP,
    Target.TASK: PageName.MISSION,
    Target.SIDEBAR: PageName.SIDEBAR,
    Target.BACKYARD: PageName.BACKYARD,
    Target.EVENT: PageName.EVENT_MAP,
}


# ── 页面控制器 ─────────────────────────────────────────────────────────────────────


class HomePage:
    """主页面的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 导航 ────────────────────────────────────────────────────────────────────

    def go_to(self, target: Target) -> None:
        """点击目标页入口。

        Args:
            target: 主页上的目标页面。

        Raises:
            ValueError: 目标页面没有配置落点。
        """
        position = constants.NAV_POSITIONS.get(target.name.lower())
        if position is None:
            raise ValueError(f'主页没有该目标的落点: {target!r}')
        _log.info('[UI] 主页面 → 进入页面：target={!r}，position={!r}', target.value, position)
        self._ctx.runtime.ctrl.click(*position)

    # ── 每日浮窗 ──────────────────────────────────────────────────────────────────

    def click_news_checkbox(self, position: tuple[float, float] | None = None) -> None:
        """点击每日公告勾选框。

        Args:
            position: 识别产出的勾选框中心；为空时使用固定落点。
        """
        self._click_overlay('news_checkbox', '勾选公告', position)

    def click_news_close(self) -> None:
        """点击关闭每日公告。"""
        self._click_overlay('news_close', '关闭公告')

    def click_reward_claim(self, position: tuple[float, float] | None = None) -> None:
        """点击每日奖励领取按钮。

        Args:
            position: 识别产出的领取按钮中心；为空时使用固定落点。
        """
        self._click_overlay('reward_claim', '领取每日奖励', position)

    def click_reward_confirm(self, position: tuple[float, float] | None = None) -> None:
        """点击奖励确认按钮。

        Args:
            position: 识别产出的确认按钮中心；为空时使用固定落点。
        """
        self._click_overlay('reward_confirm', '确认奖励', position)

    # ── 内部实现 ────────────────────────────────────────────────────────────

    def _click_overlay(
        self,
        name: str,
        action: str,
        position: tuple[float, float] | None = None,
    ) -> None:
        """点击一个每日浮窗按钮。

        Args:
            name: 按钮在 `OVERLAY_POSITIONS` 中的名称。
            action: 日志里显示的动作名。
            position: 识别产出的按钮中心；为空时使用固定落点。
        """
        target = position or constants.OVERLAY_POSITIONS[name]
        _log.info('[UI] 主页面 → {}：position={!r}', action, target)
        self._ctx.runtime.ctrl.click(*target)
