"""模块功能：提供活动页面控制器的模块入口。

上层调用：
- application.navigation：调用活动页面的前进、后退与难度切换。

下层依赖：
- event_page.page：提供页面控制器。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations

from autowsgr.application.ui.controller.home.event_page.page import EventPage


__all__ = ['EventPage']
