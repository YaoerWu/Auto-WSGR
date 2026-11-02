"""模块功能：导出建造页面控制器及其标签类型。

上层调用：
- business.logistics.build：调用建造流程入口。
- business.logistics.destroy：调用解体流程入口。
- application.navigation.registry：注册建造页面检查器。

下层依赖：
- application.ui.controller.sidebar.build_page.page：提供页面操作实现。

本模块只导出稳定的页面入口和标签类型，不执行页面操作或创建运行时上下文。
"""

__all__: list[str] = []
