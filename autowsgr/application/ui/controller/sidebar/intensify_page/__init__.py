"""模块功能：导出强化页面导航控制器。

上层调用：
- application.ui.navigation：从侧边栏进入强化页面并返回。

下层依赖：
- application.ui.controller.sidebar.intensify_page.page：提供强化页面操作实现。

边界：
本模块只声明稳定的页面导航入口，不执行页面操作、识别或运行时上下文创建。
"""

from __future__ import annotations


__all__: list[str] = []
