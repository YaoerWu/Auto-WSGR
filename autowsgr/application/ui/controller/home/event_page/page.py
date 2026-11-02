"""模块功能：控制活动页面的单次点击。

上层调用：
- application.navigation：活动页面的前进、后退与难度切换。

下层依赖：
- event_page.constants 与 event_page.stage_push：提供点击落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不解析任务参数、不编排流程、不重试。
章节标识的解析由业务层执行器的上下文预处理完成，控制器只接收落点序号；需要落点变化的
按钮（难度、确认出征）由调用方传入识别产出的中心坐标。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.home.event_page import constants
from autowsgr.application.ui.controller.home.event_page.stage_push import (
    constants as stage_push_constants,
)
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.home.event_page')


# ── 玩法落点表 ─────────────────────────────────────────────────────────────────────

# 活动玩法到章节落点表的映射。
_STAGE_POSITIONS_BY_EVENT = {
    'stage_push': stage_push_constants.STAGE_POSITIONS,
}


class EventPage:
    """活动页面的单击控制器。"""

    def __init__(self, ctx: ContextHandle, *, event_type: str = 'stage_push') -> None:
        """绑定任务上下文与活动玩法。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
            event_type: 活动玩法标识，决定使用哪一份落点表。
        """
        self._ctx = ctx
        self._event_type = event_type

    # ── 前进 ────────────────────────────────────────────────────────────────────

    def go_to_overlay(self, node: int) -> None:
        """点击第 node 个章节落点，让章节浮窗出现。

        Args:
            node: 章节落点序号，由业务层执行器的上下文预处理给出。

        Raises:
            ValueError: 活动玩法或落点序号不受支持。
        """
        positions = _STAGE_POSITIONS_BY_EVENT.get(self._event_type)
        if positions is None:
            raise ValueError(f'当前活动控制器不支持的活动玩法: {self._event_type!r}')
        if node not in positions:
            raise ValueError(f'章节落点超出范围: {node!r}')
        position = positions[node]
        _log.info('[UI] 活动页面 → 点击章节入口：node={}，position={!r}', node, position)
        self._ctx.runtime.ctrl.click(*position)

    def go_to_prepare(self, position: tuple[float, float]) -> None:
        """点击"确认出征"，从章节浮窗进入通用编队页。

        Args:
            position: 识别产出的按钮中心。
        """
        _log.info('[UI] 活动页面 → 点击确认出征：position={!r}', position)
        self._ctx.runtime.ctrl.click(*position)

    def switch_difficulty(self, position: tuple[float, float]) -> None:
        """点击难度按钮，切换普通与困难模式。

        Args:
            position: 识别产出的难度按钮中心。
        """
        _log.info('[UI] 活动页面 → 点击难度按钮：position={!r}', position)
        self._ctx.runtime.ctrl.click(*position)

    # ── 后退 ────────────────────────────────────────────────────────────────────

    def click_overlay_close(self) -> None:
        """点击浮窗关闭按钮，从章节浮窗回到活动地图。"""
        _log.info('[UI] 活动页面 → 关闭章节浮窗：position={!r}', constants.CLICK_OVERLAY_CLOSE)
        self._ctx.runtime.ctrl.click(*constants.CLICK_OVERLAY_CLOSE)

    def go_back(self) -> None:
        """点击返回按钮，从活动地图回到首页。"""
        _log.info('[UI] 活动页面 → 返回首页：position={!r}', constants.CLICK_HOME_BACK)
        self._ctx.runtime.ctrl.click(*constants.CLICK_HOME_BACK)
