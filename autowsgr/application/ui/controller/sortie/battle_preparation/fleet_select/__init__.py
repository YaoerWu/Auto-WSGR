"""模块功能：提供队伍选择控制器的模块入口。

上层调用：
- application.ui.business：获取队伍选择区域的单击控制器。

下层依赖：
- fleet_select.page：提供页面控制器与校准坐标。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.sortie.battle_preparation.fleet_select.page import (
    FLEET_TAB_CLICKS,
    SHIP_SLOT_CLICKS,
    FleetSelectPanel,
)


__all__ = [
    'FLEET_TAB_CLICKS',
    'SHIP_SLOT_CLICKS',
    'FleetSelectPanel',
]
