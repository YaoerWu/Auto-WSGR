"""模块功能：控制登录页与区服选择页的单次点击。

上层调用：
- application.ui.navigation：登录页进入游戏、打开区服列表与选择区服。

下层依赖：
- login.constants：提供进入游戏、换区入口与区服条目落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不编排启动流程、不重试。
画面确认由 login 负责，能否继续的决策由 dispatch 处理器负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.login import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.login')


# ── 页面控制器 ─────────────────────────────────────────────────────────────────────


class LoginPage:
    """登录页与区服选择页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 登录页 ───────────────────────────────────────────────────────────────────

    def click_enter_game(self, position: tuple[float, float] | None = None) -> None:
        """点击"进入游戏"按钮。

        Args:
            position: 识别产出的按钮中心；为空时使用固定落点。
        """
        target = position or constants.CLICK_ENTER_GAME
        _log.info('[UI] 登录页 → 进入游戏：position={!r}', target)
        self._ctx.runtime.ctrl.click(*target)

    def click_switch_entry(self, position: tuple[float, float] | None = None) -> None:
        """点击"点击换区"入口，让区服列表出现。

        Args:
            position: 识别产出的入口中心；为空时使用固定落点。
        """
        target = position or constants.CLICK_SWITCH_ENTRY
        _log.info('[UI] 登录页 → 打开区服列表：position={!r}', target)
        self._ctx.runtime.ctrl.click(*target)

    # ── 区服选择 ──────────────────────────────────────────────────────────────────

    def click_server(self, position: int) -> None:
        """点击第 position 个区服条目。

        Args:
            position: 区服条目序号（0 起），顺序与 `constants.SERVER_POSITIONS` 一致。

        Raises:
            ValueError: 序号超出区服条目范围。
        """
        if not 0 <= position < len(constants.SERVER_POSITIONS):
            raise ValueError(f'区服条目序号超出范围: {position!r}')
        target = constants.SERVER_POSITIONS[position]
        _log.info('[UI] 区服列表 → 选择区服：position={}，target={!r}', position, target)
        self._ctx.runtime.ctrl.click(*target)


__all__ = ['LoginPage']
