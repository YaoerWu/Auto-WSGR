"""模块功能：控制出征准备页的单次点击。

上层调用：
- application.ui.navigation：进入或离开出征准备页时调用。

下层依赖：
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不计算落点、不编排流程、不重试。
页面识别由 `navigation.checker.sortie.battle_preparation` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 左上角返回圆环的中心；准备页与出征页共用同一套标题栏布局。
CLICK_BACK = (0.0313, 0.0528)


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


__all__ = [
    'BattlePreparationPage',
]
