"""船池页面：识别与单次操作。

对外只提供页面级的识别入口与点击控制器，选船规则与流程编排由
`application.fleet_select.ship_pool` 负责。
"""

from autowsgr.application.controller.sortie.battle_preparation.ship_pool.checker import (
    ShipListText,
    check_search_input,
    check_ship_pool_page,
    read_ship_list_texts,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool.page import ShipPoolPage


__all__ = [
    'ShipListText',
    'ShipPoolPage',
    'check_search_input',
    'check_ship_pool_page',
    'read_ship_list_texts',
]
