"""模块功能：提供建造页检查器的模块入口。

上层调用：
- application.navigation：调用建造页与标签的确认入口。

下层依赖：
- build.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sidebar.build.checker import (
    check_build_page,
    check_dismantle_tab,
)
from autowsgr.application.controller.sidebar.build.page import (
    BuildPage,
    BuildTab,
)


__all__ = [
    'BuildPage',
    'BuildTab',
    'check_build_page',
    'check_dismantle_tab',
]
