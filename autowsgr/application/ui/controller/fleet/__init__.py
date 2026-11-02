"""模块功能：提供 Fleet UI Controller 的稳定页面入口。

上层调用：
- business.combat、application.navigation：创建出征准备页控制器。

下层依赖：
- main_page：提供出征准备页面 UI 和主流程。
"""

from typing import TYPE_CHECKING

import numpy

from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import (
    FleetSnapshot,
)
from autowsgr.application.ui.controller.fleet.main_page import BattlePreparationPage, Panel
from autowsgr.application.ui.controller.fleet.support.repair import RepairStrategy
from autowsgr.application.navigation.types import PageMatch


def check_ship_selection_page(screen: numpy.ndarray) -> PageMatch:
    """提供导航注册使用的船池页面只读检查入口。"""
    from autowsgr.application.ui.controller.fleet.formation.ship_selection import (
        ShipSelectionPage,
    )

    return ShipSelectionPage.check_current_page(screen)


__all__ = [
    'BattlePreparationPage',
    'FleetSnapshot',
    'Panel',
    'RepairStrategy',
    'check_ship_selection_page',
]
