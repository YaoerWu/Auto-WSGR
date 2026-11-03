"""模块功能：提供快速整备检查器的模块入口。

上层调用：
- 暂无生产调用方：整备流程接线（任务书 P4）后由应用层通过本入口读取整备事实。

下层依赖：
- application.controller.sortie.battle_preparation.quick_maintenance.checker：提供识别入口。
- application.controller.sortie.battle_preparation.quick_maintenance.page：提供面板点击入口。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.checker import (
    check_auto_supply_enabled,
    check_quick_repair_active,
    read_all_repair_center,
    read_auto_supply_center,
    read_quick_repair_center,
    read_repair_tool_count,
)
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.page import (
    QuickMaintenancePanel,
)


__all__ = [
    'QuickMaintenancePanel',
    'check_auto_supply_enabled',
    'check_quick_repair_active',
    'read_all_repair_center',
    'read_auto_supply_center',
    'read_quick_repair_center',
    'read_repair_tool_count',
]
