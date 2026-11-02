"""模块功能：在任务页执行领奖与返回。

上层调用：
- application.ui.navigation：执行任务页的领奖与返回主页的页面边动作。

下层依赖：
- application.ui.controller.operations.mission_page.constants：提供点击落点。

边界：只点击领奖按钮与返回按钮，不识别画面、不确认终态、不挑选具体任务。
任务列表的逐条挑选与滚动属于旧业务，已随架构升级移除；领奖统一走「全部领取」。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.operations.mission_page import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.mission_page')


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class MissionPage:
    """任务页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 领奖 ────────────────────────────────────────────────────────────────

    def click_claim_all(self) -> None:
        """点击右下角「全部领取」。

        按钮只在有奖励可领时出现；是否出现由导航器先用 `check_claim_all_button`
        判断，本方法不做识别。
        """
        _log.info('[UI] 任务页 → 全部领取：position={!r}', constants.CLICK_CLAIM_ALL)
        self._ctx.runtime.ctrl.click(*constants.CLICK_CLAIM_ALL)

    def click_reward_confirm(self) -> None:
        """点击「获得」浮窗里的「确认」，关闭浮窗。"""
        _log.info('[UI] 任务页 → 确认领奖：position={!r}', constants.CLICK_REWARD_CONFIRM)
        self._ctx.runtime.ctrl.click(*constants.CLICK_REWARD_CONFIRM)

    # ── 返回 ────────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击左上角返回按钮，离开任务页。"""
        _log.info('[UI] 任务页 → 返回：position={!r}', constants.CLICK_BACK)
        self._ctx.runtime.ctrl.click(*constants.CLICK_BACK)


__all__ = ['MissionPage']
