"""模块功能：战斗阶段识别与战果读取入口。

上层调用：
- controller.sortie.battle_engine：统一转出。
- application.combat.engine：直接取阶段识别与战果读取函数。

下层依赖：
- battle_engine.monitor.types：阶段枚举。
- battle_engine.monitor.constants：阶段签名与识别校准。
- battle_engine.monitor.checker：识别实现。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    ShipDropResult,
    check_ship_drop_page,
    check_template_exist,
    is_ship_drop_page,
    read_combat_phase,
    read_enemy_composition,
    read_enemy_formation,
    read_mvp,
    read_phase_from_frame,
    read_result_grade,
    read_ship_drop,
    read_ship_stats,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.constants import (
    PHASE_SIGNATURES,
    PhaseSignature,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase


__all__ = [
    'PHASE_SIGNATURES',
    'CombatPhase',
    'PhaseSignature',
    'ShipDropResult',
    'check_ship_drop_page',
    'check_template_exist',
    'is_ship_drop_page',
    'read_combat_phase',
    'read_enemy_composition',
    'read_enemy_formation',
    'read_mvp',
    'read_phase_from_frame',
    'read_result_grade',
    'read_ship_drop',
    'read_ship_stats',
]
