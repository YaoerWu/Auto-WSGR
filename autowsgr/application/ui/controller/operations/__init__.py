"""模块功能：组织首页右下角同级的任务、船坞和出征功能区域。

上层调用：
- application.ui.controller.home.main_page：从首页进入 operations 区域内的页面。
- application.navigation：注册并执行区域内页面的导航边。

下层依赖：
- application.ui.controller.operations.mission_page：提供任务页面控制器。
- application.ui.controller.operations.sortie_page：提供顶部标签面板 Mixin。

本包只表达同级功能区域的目录归属，不聚合导入子页面，也不保存运行时状态。
"""
