"""模块功能：用离线帧替身验证「识别 → 派发 → 转移」这条主链路。

直接调用方：pytest。

直接依赖：application.combat.engine.loop 与 transitions。

边界：只替换识别器与两个会碰设备的处理器，不连设备、不读截图、不读模板文件。
"""

from __future__ import annotations

from typing import Any

from autowsgr.application.combat.history import EventType
from autowsgr.application.combat.engine.loop import CombatLoop
from autowsgr.application.combat.engine.transitions import build_transitions
from autowsgr.application.combat.engine.types import CombatPhase
from autowsgr.application.combat.types import (
    CombatMode,
    ConditionFlag,
    FightCondition,
    ModeCategory,
    ShipDamageState,
)


class FakeNodeDecision:
    """节点决策替身：不迂回、进战斗、打夜战。"""

    SL_when_enter_fight = False
    night = True


class FakePlan:
    """战斗计划替身，只实现主循环真正读到的字段。"""

    def __init__(self, mode: str, end_phase: CombatPhase) -> None:
        """按模式与结束页搭出最小计划。"""
        self.mode = mode
        self.collect_result_info = True
        self.end_phase = end_phase
        self.fight_condition = FightCondition.aim
        self.transitions = build_transitions(ModeCategory.SINGLE, end_phase)

    def get_node_decision(self, node: str) -> FakeNodeDecision:
        """任何节点都返回同一份决策。"""
        del node
        return FakeNodeDecision()


class FakeRecognizer:
    """按预设顺序吐阶段的识别器替身，并记下每次被问到的候选。"""

    def __init__(self, phases: list[CombatPhase]) -> None:
        """按给定顺序排好要返回的阶段。"""
        self._phases = list(phases)
        self.candidates: list[list[CombatPhase]] = []

    def wait_for_phase(
        self,
        candidates: list[CombatPhase],
        *,
        poll_action: Any = None,
    ) -> CombatPhase:
        """记录候选后立即返回下一个预定阶段，不执行轮询动作。"""
        del poll_action
        self.candidates.append(list(candidates))
        return self._phases.pop(0)


def test_dock_full_ends_battle_without_success() -> None:
    """船坞满直接结束整场，不改写成功标志。"""
    plan = FakePlan(CombatMode.DECISIVE, CombatPhase.RESULT)
    loop = CombatLoop(object())
    loop._recognizer = FakeRecognizer([CombatPhase.DOCK_FULL])

    result = loop.run(plan, [ShipDamageState.NORMAL] * 6)

    assert result.flag is ConditionFlag.DOCK_FULL
    assert [event.event_type for event in result.history.events] == [EventType.AUTO_RETURN]
    assert result.history.events[0].action == '船坞已满'


def test_phase_dispatch_follows_transition_graph(monkeypatch: Any) -> None:
    """每一轮候选都来自上一阶段的转移图，夜战分支按决策选中。"""
    clicks: list[bool] = []
    handled: list[CombatPhase] = []

    def fake_click_night_battle(ctx: Any, *, pursue: bool) -> None:
        del ctx
        clicks.append(pursue)

    def fake_handle_result(mixin: Any) -> ConditionFlag:
        del mixin
        handled.append(CombatPhase.RESULT)
        return ConditionFlag.FIGHT_CONTINUE

    monkeypatch.setattr(
        'autowsgr.application.combat.engine.handlers.click_night_battle',
        fake_click_night_battle,
    )
    monkeypatch.setattr(
        'autowsgr.application.combat.engine.settlement.CombatSettlementMixin._handle_result',
        fake_handle_result,
    )

    plan = FakePlan(CombatMode.DECISIVE, CombatPhase.RESULT)
    loop = CombatLoop(object())
    recognizer = FakeRecognizer(
        [
            CombatPhase.FIGHT_PERIOD,
            CombatPhase.NIGHT_PROMPT,
            CombatPhase.RESULT,
        ],
    )
    loop._recognizer = recognizer

    result = loop.run(plan, [ShipDamageState.NORMAL] * 6)

    assert result.flag is ConditionFlag.OPERATION_SUCCESS
    assert clicks == [True]
    assert handled == [CombatPhase.RESULT]
    assert recognizer.candidates == [
        [
            CombatPhase.SPOT_ENEMY_SUCCESS,
            CombatPhase.FORMATION,
            CombatPhase.FIGHT_PERIOD,
            CombatPhase.DOCK_FULL,
        ],
        [CombatPhase.NIGHT_PROMPT, CombatPhase.RESULT],
        [CombatPhase.RESULT],
    ]
    assert [event.event_type for event in result.history.events] == [
        EventType.NIGHT_BATTLE,
        EventType.AUTO_RETURN,
    ]
