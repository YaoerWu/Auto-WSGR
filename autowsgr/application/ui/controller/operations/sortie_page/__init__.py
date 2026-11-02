"""模块功能：组织 sortie_page 的六个垂直页面模块。

上层调用：
- application.navigation、business 和 testing.ui：直接调用各具体页面包的稳定入口。

下层依赖：
- application.ui.controller.operations.sortie_page.main_page：提供 sortie_page 页面壳和顶部标签。
- application.ui.controller.operations.sortie_page.*_page：提供各出征模式页面行为。

本包只负责目录边界，不聚合不同出征模式的页面控制器，也不保存运行时状态。
"""

__all__: list[str] = []
