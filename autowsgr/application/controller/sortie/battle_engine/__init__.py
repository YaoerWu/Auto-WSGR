"""模块功能：战斗引擎在 controller 层的识别与点击入口。

上层调用：
- application.combat.engine：按当前阶段点击、判阶段、读战果与船位。

下层依赖：
- battle_engine.page：战斗内点击动作。
- battle_engine.monitor：阶段识别与战果读取。
- battle_engine.tracking：地图船只位置观测。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    read_combat_phase,
    read_phase_from_frame,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase
from autowsgr.application.controller.sortie.battle_engine.page import (
    click_enter_fight,
    click_fight_condition,
    click_formation,
    click_night_battle,
    click_proceed,
    click_result,
    click_retreat,
    click_skip_missile_animation,
    click_speed_up,
    click_template,
    dismiss_resource_confirm,
)
from autowsgr.application.controller.sortie.battle_engine.tracking.checker import (
    check_spot_page,
    read_ship_position,
    read_yellow_cluster,
)


__all__ = [
    'CombatPhase',
    'check_spot_page',
    'click_enter_fight',
    'click_fight_condition',
    'click_formation',
    'click_night_battle',
    'click_proceed',
    'click_result',
    'click_retreat',
    'click_skip_missile_animation',
    'click_speed_up',
    'click_template',
    'dismiss_resource_confirm',
    'read_combat_phase',
    'read_phase_from_frame',
    'read_ship_position',
    'read_yellow_cluster',
]
