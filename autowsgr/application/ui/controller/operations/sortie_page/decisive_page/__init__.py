"""模块功能：导出决战总览、地图和出征准备页面控制器。

上层调用：
- application.navigation：注册决战总览页并执行决战回退导航。
- business.combat.decisive：驱动决战地图、战备舰队和出征准备流程。
- testing.ui：验证决战页面控制器。

下层依赖：
- application.ui.controller.operations.sortie_page.decisive_page.page：提供总览页操作。
- application.ui.controller.operations.sortie_page.decisive_page.map_page：提供地图页操作。
- application.ui.controller.fleet：提供统一准备页入口。

本包只导出稳定页面入口；校准、识别和旧编队兼容实现由子模块负责。
"""

from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.map_page import (
    DecisiveMapController,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.page import (
    DecisiveBattlePage,
    DecisiveEntryPage,
)


__all__ = [
    'DecisiveBattlePage',
    'DecisiveEntryPage',
    'DecisiveMapController',
]
