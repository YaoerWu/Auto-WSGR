"""模块功能：提供出征准备页检查器的模块入口。

上层调用：
- application.navigation：判断当前属于哪一种出征准备页，离开准备页时点返回。
- application.fleet_select.operation.team_select：读取并切换当前舰队编号。

下层依赖：
- application.controller.sortie.battle_preparation.checker：提供识别入口。
- application.controller.sortie.battle_preparation.page：提供单击入口。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.checker import (
    read_battle_preparation_layer,
    read_team_tab,
)
from autowsgr.application.controller.sortie.battle_preparation.page import BattlePreparationPage


__all__ = [
    'BattlePreparationPage',
    'read_battle_preparation_layer',
    'read_team_tab',
]
