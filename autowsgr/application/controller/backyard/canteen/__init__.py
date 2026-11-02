"""模块功能：提供餐厅二级页检查器的模块入口。

上层调用：
- application.navigation：调用餐厅二级页的确认入口。

下层依赖：
- canteen.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.backyard.canteen.checker import (
    check_canteen_page,
)
from autowsgr.application.controller.backyard.canteen.page import CanteenPage


__all__ = [
    'CanteenPage',
    'check_canteen_page',
]
