"""模块功能：提供后院检查器的模块入口。

上层调用：
- application.ui.navigation：调用后院主页与四个二级页的确认入口。

下层依赖：
- backyard.checker：提供后院主页的确认入口与四个入口中心；
- backyard 下四个页面子包：各自提供本页的确认入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.backyard.academy import check_academy_page
from autowsgr.application.controller.backyard.bath import check_bath_page
from autowsgr.application.controller.backyard.canteen import check_canteen_page
from autowsgr.application.controller.backyard.checker import (
    check_backyard_page,
    read_academy_entry_center,
    read_bath_entry_center,
    read_canteen_entry_center,
    read_rank_room_entry_center,
)
from autowsgr.application.controller.backyard.page import (
    BackyardPage,
    BackyardTarget,
)
from autowsgr.application.controller.backyard.rank_room import (
    check_rank_room_page,
)


__all__ = [
    'BackyardPage',
    'BackyardTarget',
    'check_academy_page',
    'check_backyard_page',
    'check_bath_page',
    'check_canteen_page',
    'check_rank_room_page',
    'read_academy_entry_center',
    'read_bath_entry_center',
    'read_canteen_entry_center',
    'read_rank_room_entry_center',
]
