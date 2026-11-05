"""模块功能：战斗战果与掉落的业务解释。

战斗结束后读等级、读血条、读 MVP，写进战斗历史；掉落页再补一条掉落记录。

上层调用：
- application.combat.engine.handlers：RESULT 与 GET_SHIP 阶段的处理。

下层依赖：
- controller.sortie.battle_engine.monitor：战果页识别。
- application.combat.history：战斗事件与战果记录。

边界：只解释战果并记账；不点按钮、不推进状态机。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.combat.engine.types import CombatPhase
from autowsgr.application.combat.errors import CombatRecognitionTimeoutError
from autowsgr.application.combat.history import CombatEvent, CombatHistory, EventType, FightResult
from autowsgr.application.combat.types import ConditionFlag, ShipDamageState
from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    read_mvp,
    read_result_grade,
    read_ship_drop,
    read_ship_stats,
)
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.combat.types import BattlePlan
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')

_RESULT_SETTLE_SECONDS = 1.5
"""战果页出现后等待动画稳定再识别的时间。"""


class CombatSettlementMixin:
    """识别战果并记录战斗业务结果。

    Attributes:
        _ctx: 提供设备服务的统一 ContextHandle。
        _plan: 当前作战计划。
        _node: 当前所在节点名。
        _ship_stats: 六槽位血量状态。
        _history: 战斗历史。
    """

    _ctx: ContextHandle
    _plan: BattlePlan
    _node: str
    _ship_stats: list[ShipDamageState]
    _history: CombatHistory

    # ── 战果解释 ─────────────────────────────────────────────

    def _handle_result(self) -> ConditionFlag:
        """识别战果并记录业务结果。

        Returns:
            战果页处理完返回 FIGHT_CONTINUE。
        """
        time.sleep(_RESULT_SETTLE_SECONDS)
        grade = read_result_grade(self._ctx)
        if not grade:
            raise CombatRecognitionTimeoutError('战果识别超时：未识别到评级')
        self._ship_stats = read_ship_stats(self._ctx, self._ship_stats)
        mvp = read_mvp(self._ctx)
        fight_result = FightResult(
            node=self._node,
            mvp=mvp,
            grade=grade,
            ship_stats=self._ship_stats[:],
        )
        self._history.add(
            CombatEvent(
                event_type=EventType.RESULT,
                node=self._node,
                result=grade,
                ship_stats=self._ship_stats[:],
                extra={'mvp': mvp},
            )
        )
        _log.info('[COMBAT] 战果：{} 节点：{}', fight_result, self._node)
        if self._plan.collect_result_info:
            self._click_result_until_closed(CombatPhase.RESULT)
        else:
            self._click_result_until_closed(
                CombatPhase.RESULT,
                pass_through=(CombatPhase.EXP_SETTLEMENT,),
            )
        return ConditionFlag.FIGHT_CONTINUE

    def _capture_get_ship(self) -> str | None:
        """识别并幂等记录掉落舰船。

        Returns:
            本次掉落的舰名；同一节点已记过或未识别到舰名时为空。
        """
        existing = self._history.get_event(EventType.GET_SHIP, self._node)
        if existing is not None:
            return existing.result or None
        drop = read_ship_drop(self._ctx)
        if not drop.ship_name:
            return None
        _log.info('[COMBAT] 获得舰船：{}', drop.ship_name)
        self._history.add(
            CombatEvent(
                event_type=EventType.GET_SHIP,
                node=self._node,
                result=drop.ship_name,
            )
        )
        return drop.ship_name


__all__ = ['CombatSettlementMixin']
