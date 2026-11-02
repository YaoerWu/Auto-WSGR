"""模块功能：应用层导航器包。

上层调用：
- application 与 business：从 navigation.service 导入 NavigationService。

下层依赖：
- executor、registry、service 和 types 四个子模块。

本包入口不导出实现：控制器需要 navigation.types，如果包入口顺带加载 service，
就会与控制器的页面模块形成循环导入。调用方直接从 service 导入。
"""

__all__: list[str] = []
