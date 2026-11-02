"""模块功能：提供快速整备检查器的模块入口。

上层调用：
- application.navigation：读血条状态、快速修理与自动补给的事实。

下层依赖：
- quick_maintenance.checker：提供识别入口与船损状态模型。

本模块只导出稳定入口与事实模型，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.checker import (
    ShipDamage,
    check_auto_supply_enabled,
    check_quick_repair_active,
    read_all_repair_center,
    read_auto_supply_center,
    read_quick_repair_center,
    read_repair_tool_count,
    read_ship_damage,
)
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.page import (
    QuickMaintenancePanel,
)


__all__ = [
    'QuickMaintenancePanel',
    'ShipDamage',
    'check_auto_supply_enabled',
    'check_quick_repair_active',
    'read_all_repair_center',
    'read_auto_supply_center',
    'read_quick_repair_center',
    'read_repair_tool_count',
    'read_ship_damage',
]
