"""模块功能：船池页面的公开出口，只汇总识别入口与点击控制器。

上层调用：
- application.fleet_select.operation.ship_select：用识别结果决定点哪张卡，再调用这里的原子点击。
- application.navigation.registry：把船池页面登记为一个可导航页面。

下层依赖：
- application.controller.sortie.battle_preparation.ship_pool.checker：页面事实识别。
- application.controller.sortie.battle_preparation.ship_pool.page：单次点击与滚动。

边界：不含选船规则与流程编排，那部分归 application.fleet_select.operation.ship_select。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.ship_pool.checker import (
    ShipListText,
    ShipPoolKind,
    check_search_input,
    check_ship_pool_page,
    read_ship_list_texts,
    read_ship_pool_kind,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool.page import ShipPoolPage


__all__ = [
    'ShipListText',
    'ShipPoolKind',
    'ShipPoolPage',
    'check_search_input',
    'check_ship_pool_page',
    'read_ship_list_texts',
    'read_ship_pool_kind',
]
