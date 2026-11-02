"""模块功能：承载控制器层的页面识别与状态判定实现。

上层调用：
- application.ui.navigation.registry：按页面取用对应的到达确认入口。
- application.ui.controller 下各页面：按页面语义取用状态判定与落点读取。

下层依赖：
- common.vision：模板匹配、OCR 与像素识别。
- common.system：日志与公共基础类型。

只做页面归属与状态判定，不放导航编排与点击操作。
"""

__all__: list[str] = []
