"""模块功能：控制战术支援按钮与浮窗的单次点击。

上层调用：
- 战术支援业务编排：点开浮窗、点浮窗里的开关按钮。

下层依赖：
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不判断点完有没有生效、不编排流程。
页面识别由 `controller.sortie.battle_preparation.tactical_support.checker` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.tactical_support import (
    constants,
)


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 右上角第二格战术支援按钮的中心，取已开启态模板的几何中心。
constants.CLICK_SUPPORT_BUTTON = (0.6617, 0.1653)

# 浮窗里开关按钮的中心；开关文案随状态变化，落点不变。
constants.CLICK_TOGGLE_BUTTON = (0.7906, 0.5028)


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class TacticalSupportPage:
    """战术支援按钮与浮窗的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def click_support_button(self, center: tuple[float, float] | None = None) -> None:
        """点击右上角的战术支援按钮，打开浮窗。

        Args:
            center: 按钮的归一化中心；省略时用校准落点，适合按钮还没点亮、识别不到的时候。
        """
        self._ctx.runtime.ctrl.click(*(center or constants.CLICK_SUPPORT_BUTTON))

    def click_toggle_button(self, center: tuple[float, float] | None = None) -> None:
        """点击浮窗里的开关按钮，切换开启与关闭。

        Args:
            center: 开关按钮的归一化中心；省略时用校准落点。
        """
        self._ctx.runtime.ctrl.click(*(center or constants.CLICK_TOGGLE_BUTTON))


__all__ = ['TacticalSupportPage']
