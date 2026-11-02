"""模块功能：提供好友页面检查器的模块入口。

上层调用：
- application.ui.navigation：调用好友页面的确认入口。

下层依赖：
- friend.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sidebar.friend.checker import (
    check_friend_page,
)
from autowsgr.application.controller.sidebar.friend.page import FriendPage


__all__ = [
    'FriendPage',
    'check_friend_page',
]
