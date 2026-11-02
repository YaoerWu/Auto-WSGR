"""模块功能：提供普通出征章节检查器的模块入口。

上层调用：
- application.navigation：按入参选到指定章节与地图节点。

下层依赖：
- battle.checker：提供页内导航入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.battle.checker import ensure_chapter
from autowsgr.application.controller.sortie.battle.page import BattlePage


__all__ = [
    'BattlePage',
    'ensure_chapter',
]
