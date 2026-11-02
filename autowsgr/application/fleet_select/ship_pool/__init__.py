"""船池换船编排：搜索、找卡、移除。

对外只提供单槽的换船与清空两个入口，全局分配与整队复查由
`application.fleet_select.battle_preparation` 负责。
"""

from autowsgr.application.fleet_select.ship_pool.workflow import remove_ship, select_ship


__all__ = ['remove_ship', 'select_ship']
