"""模块功能：提供学院二级页检查器的模块入口。

上层调用：
- application.navigation：调用学院二级页的确认入口。

下层依赖：
- academy.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.backyard.academy.checker import (
    check_academy_page,
)
from autowsgr.application.controller.backyard.academy.page import AcademyPage


__all__ = [
    'AcademyPage',
    'check_academy_page',
]
