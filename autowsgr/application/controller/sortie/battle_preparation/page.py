"""模块功能：控制出征准备页的单次点击。

上层调用：
- application.navigation：离开出征准备页时点左上角返回。
- application.fleet_select.operation.team_select：切换舰队时点目标队标签。

下层依赖：
- autowsgr.application.controller.sortie.battle_preparation.constants：提供返回与舰队标签落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不计算落点、不编排流程、不重试。
页面识别由 `controller.sortie.battle_preparation` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation import (
    constants,
)


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class BattlePreparationPage:
    """出征准备页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def go_back(self) -> None:
        """点击返回按钮，退回到出征页。"""
        self._ctx.runtime.ctrl.click(*constants.CLICK_BACK)

    def click_team_tab(self, team: int) -> None:
        """点击第 N 舰队的标签页。

        Args:
            team: 舰队编号，1 到 4。

        Raises:
            ValueError: 舰队编号超出 1 到 4 的范围。
        """
        if not 1 <= team <= len(constants.CLICK_TEAM_TABS):
            raise ValueError(
                f'舰队编号必须在 1 到 {len(constants.CLICK_TEAM_TABS)} 之间，实际为 {team}'
            )
        self._ctx.runtime.ctrl.click(*constants.CLICK_TEAM_TABS[team - 1])


__all__ = ['BattlePreparationPage']
