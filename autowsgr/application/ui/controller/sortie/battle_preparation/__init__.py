"""模块功能：提供出征准备页控制器的模块入口。

上层调用：
- application.ui.business：获取出征准备页的队伍选择控制器。

下层依赖：
- battle_preparation.fleet_select：提供队伍选择控制器。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.sortie.battle_preparation.fleet_select import (
    FleetSelectPanel,
)


__all__ = [
    'FleetSelectPanel',
]
