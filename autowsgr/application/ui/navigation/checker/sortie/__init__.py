"""模块功能：提供出征页检查器的模块入口。

上层调用：
- application.ui.navigation：读取当前能同时看到的出征页体系页面层。

下层依赖：
- sortie.checker：提供识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.ui.navigation.checker.sortie.checker import read_sortie_layer


__all__ = ['read_sortie_layer']
