"""模块功能：战斗监控子包。

从点下【开始出征】到退出战果页这一段：等阶段、按阶段决策、读战果。

上层调用：
- application.combat.service：发起一场战斗。

边界：不负责进图选章、编队换船、补给修理，也不决定打几场。
"""

from autowsgr.application.combat.engine.loop import CombatLoop
from autowsgr.application.combat.engine.recognizer import CombatRecognizer
from autowsgr.application.combat.engine.transitions import (
    MODE_CATEGORIES,
    MODE_END_PHASES,
    MODE_SPECS,
    build_transitions,
    resolve_successors,
)
from autowsgr.application.combat.engine.types import CombatPhase, PhaseBranch


__all__ = [
    'MODE_CATEGORIES',
    'MODE_END_PHASES',
    'MODE_SPECS',
    'CombatLoop',
    'CombatPhase',
    'CombatRecognizer',
    'PhaseBranch',
    'build_transitions',
    'resolve_successors',
]
