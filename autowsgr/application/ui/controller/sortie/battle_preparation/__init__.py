"""模块功能：提供出征准备页控制器的模块入口。

上层调用：
- application.ui.navigation：获取出征准备页的页面控制器。

下层依赖：
- battle_preparation.page：提供页面控制器。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.sortie.battle_preparation.page import (
    BattlePreparationPage,
)


__all__ = [
    'BattlePreparationPage',
]
