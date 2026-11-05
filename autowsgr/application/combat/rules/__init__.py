"""模块功能：战斗的规则判定层。

上层调用：
- application.combat.engine：按规则决定撤退、迂回、阵型与是否继续前进。

边界：纯判定，输入局面数据、输出动作；不认画面、不点按钮、不写历史。
"""

from autowsgr.application.combat.rules.enemy import (
    Condition,
    Rule,
    RuleAction,
    RuleEngine,
    RuleResult,
)
from autowsgr.application.combat.rules.node import check_blood


__all__ = [
    'Condition',
    'Rule',
    'RuleAction',
    'RuleEngine',
    'RuleResult',
    'check_blood',
]
