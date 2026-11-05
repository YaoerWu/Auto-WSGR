"""模块功能：战斗阶段的类型出口。

阶段枚举的唯一来源是 checker：它要返回这个值，必须由下层定义，引擎再转出。

上层调用：
- application.combat.engine 内各子模块：状态机流转、阶段分派。
- application.combat.engine.transitions：构建转移图。
- business.combat.plan：转移图的类型标注。

下层依赖：
- controller.sortie.battle_engine.monitor.types：CombatPhase。

边界：只做转出与分支类型别名；不持有运行时状态、不读写设备。
"""

from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase


PhaseBranch = list[CombatPhase] | dict[str, list[CombatPhase]]
"""分支定义：无条件列表，或按动作名索引的字典。"""


__all__ = ['CombatPhase', 'PhaseBranch']
