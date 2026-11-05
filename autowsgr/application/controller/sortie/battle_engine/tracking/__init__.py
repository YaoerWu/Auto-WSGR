"""模块功能：地图船只位置观测入口。

上层调用：
- controller.sortie.battle_engine：统一转出。
- application.combat.node_tracking.tracker：每轮读一次船位。

下层依赖：
- battle_engine.tracking.checker：观测实现。
- battle_engine.tracking.constants：像素校准。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.battle_engine.tracking.checker import (
    check_ship_icon,
    check_spot_page,
    read_ship_position,
    read_ship_position_from_frame,
    read_yellow_cluster,
)


__all__ = [
    'check_ship_icon',
    'check_spot_page',
    'read_ship_position',
    'read_ship_position_from_frame',
    'read_yellow_cluster',
]
