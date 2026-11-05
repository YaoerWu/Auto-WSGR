"""模块功能：战斗引擎包。

对外只有一个入口 run_battle：给一份战斗计划开战前状态，内部跑完一整场，返回
战果。战斗内部分四块：准备阶段编排、战斗监控、战斗决策、战斗结果识别；地图
节点追踪单独成子包，规则与操作分层放在 rules 与 operation。

上层调用：
- business.combat 各模式：编排层决定打几场、打完去哪，战斗本身交给这里。

边界：不负责进图选章、编队换船、补给修理。
"""

from autowsgr.application.combat.engine.transitions import (
    ModeCategory,
    build_transitions,
    resolve_successors,
)
from autowsgr.application.combat.engine.types import CombatPhase, PhaseBranch
from autowsgr.application.combat.errors import (
    CombatError,
    CombatRecognitionTimeoutError,
    CombatStopRequestedError,
)
from autowsgr.application.combat.history import (
    CombatEvent,
    CombatHistory,
    CombatResult,
    EventType,
    FightResult,
    grade_condition_met,
)
from autowsgr.application.combat.node_tracking import MapNodeData, NodePosition, NodeTracker
from autowsgr.application.combat.service import run_battle
from autowsgr.application.combat.types import (
    CombatMode,
    ConditionFlag,
    FightCondition,
    Formation,
    RepairMode,
    SearchEnemyAction,
    ShipDamageState,
)


__all__ = [
    'CombatError',
    'CombatEvent',
    'CombatHistory',
    'CombatMode',
    'CombatPhase',
    'CombatRecognitionTimeoutError',
    'CombatResult',
    'CombatStopRequestedError',
    'ConditionFlag',
    'EventType',
    'FightCondition',
    'FightResult',
    'Formation',
    'MapNodeData',
    'ModeCategory',
    'NodePosition',
    'NodeTracker',
    'PhaseBranch',
    'RepairMode',
    'SearchEnemyAction',
    'ShipDamageState',
    'build_transitions',
    'grade_condition_met',
    'resolve_successors',
    'run_battle',
]
