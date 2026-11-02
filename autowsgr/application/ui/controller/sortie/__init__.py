"""模块功能：提供出征相关页面控制器的模块入口。

上层调用：
- application.navigation：获取出征准备页与演习页的页面控制器。

下层依赖：
- sortie.battle_preparation：提供出征准备页控制器。
- sortie.exercise：提供演习页控制器。

本模块只导出稳定入口，不放业务实现。
"""

from __future__ import annotations


__all__: list[str] = []
