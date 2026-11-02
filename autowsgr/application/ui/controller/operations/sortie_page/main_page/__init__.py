"""模块功能：提供出征页页面壳控制器的模块入口。

上层调用：
- application.ui.navigation：调用出征页的标签切换与返回。
- application.ui.controller.operations.sortie_page.*_page：复用标签枚举。

下层依赖：
- main_page.page：提供页面控制器与标签枚举。

本模块只导出稳定入口，不放业务实现；远征通知识别按需从 `main_page.recognition` 直接导入。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.operations.sortie_page.main_page.recognition import (
    check_expedition_notification,
)


__all__ = [
    'check_expedition_notification',
]
