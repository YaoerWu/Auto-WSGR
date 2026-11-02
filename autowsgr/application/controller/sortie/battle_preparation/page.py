"""模块功能：控制出征准备页的单次点击。

上层调用：
- application.navigation：进入或离开出征准备页时调用。

下层依赖：
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不计算落点、不编排流程、不重试。
页面识别由 `controller.sortie.battle_preparation` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 左上角返回圆环的中心；准备页与出征页共用同一套标题栏布局。
CLICK_BACK = (0.0313, 0.0528)

# 四个舰队标签页的中心，按 1、2、3、4 队顺序；取各自高亮块模板的几何中心。
CLICK_TEAM_TABS: tuple[tuple[float, float], ...] = (
    (0.1113, 0.1618),
    (0.2348, 0.1618),
    (0.3582, 0.1611),
    (0.4824, 0.1618),
)


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
        self._ctx.runtime.ctrl.click(*CLICK_BACK)

    def click_team_tab(self, team: int) -> None:
        """点击第 N 舰队的标签页。

        Args:
            team: 舰队编号，1 到 4。

        Raises:
            ValueError: 舰队编号超出 1 到 4 的范围。
        """
        if not 1 <= team <= len(CLICK_TEAM_TABS):
            raise ValueError(f'舰队编号必须在 1 到 {len(CLICK_TEAM_TABS)} 之间，实际为 {team}')
        self._ctx.runtime.ctrl.click(*CLICK_TEAM_TABS[team - 1])


__all__ = [
    'CLICK_BACK',
    'CLICK_TEAM_TABS',
    'BattlePreparationPage',
]
