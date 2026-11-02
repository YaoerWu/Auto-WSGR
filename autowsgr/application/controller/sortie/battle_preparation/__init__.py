"""模块功能：提供出征准备页检查器的模块入口。

上层调用：
- application.ui.navigation：调用出征准备页的识别入口。

下层依赖：
- battle_preparation.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.battle_preparation.checker import (
    read_battle_preparation_layer,
)
from autowsgr.application.controller.sortie.battle_preparation.page import BattlePreparationPage


__all__ = [
    'BattlePreparationPage',
    'read_battle_preparation_layer',
]
