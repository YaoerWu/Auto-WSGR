"""模块功能：提供普通出征章节、地图和出征准备入口。

上层调用：
- business.combat.bettle：定位普通出征地图并进入出征准备。
- application.runtime.context：读取普通出征地图统计。
- application.navigation：使用页面检查器识别 sortie_page 壳。
- testing.ui、tools：验证普通出征页面行为。

下层依赖：
- application.ui.controller.operations.sortie_page.main_page：提供 sortie_page 页面壳。
- application.ui.controller.operations.sortie_page.battle_page.page：提供普通出征页面动作。
- application.ui.controller.operations.sortie_page.battle_page.recognition：提供章节和地图 OCR。

本包只导出普通出征页面的稳定入口，不聚合其他出征模式。
"""

__all__: list[str] = []
