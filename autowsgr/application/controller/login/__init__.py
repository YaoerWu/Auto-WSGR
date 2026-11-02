"""模块功能：提供登录流程 checker 的模块入口。

上层调用：
- application.ui.navigation：把登录相关画面注册为到达确认；
- application.ui.navigation.service：启动流程按顺序判断当前画面。

下层依赖：
- login.checker：提供画面判断与区服定位。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.login.checker import (
    check_black_screen,
    check_loading,
    check_login_page,
    check_server_select,
    check_update_prompt,
    get_server_index,
    read_enter_button_center,
    read_server_index,
    read_server_position,
    read_switch_entry_center,
)
from autowsgr.application.controller.login.page import LoginPage


__all__ = [
    'LoginPage',
    'check_black_screen',
    'check_loading',
    'check_login_page',
    'check_server_select',
    'check_update_prompt',
    'get_server_index',
    'read_enter_button_center',
    'read_server_index',
    'read_server_position',
    'read_switch_entry_center',
]
