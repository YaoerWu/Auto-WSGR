"""模块功能：提供主页控制器的模块入口。

上层调用：
- application.navigation：调用主页导航与每日浮窗按钮点击。
- business.logistics：读取主页通知状态。

下层依赖：
- main_page.page：提供页面控制器与导航目标。
- main_page.recognition：提供通知识别。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.home.main_page.recognition import (
    check_expedition_ready,
    check_task_ready,
)


__all__ = [
    'check_expedition_ready',
    'check_task_ready',
]
