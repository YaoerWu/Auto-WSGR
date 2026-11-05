"""模块功能：战斗编排层。

决定打几场、去哪打、什么时候换船修理，然后把每一场交给战斗引擎。战斗本身（从
点下出征到退出战果页）不在这里实现，在 application.combat。

当前成员：
- bettle/：普通出征与活动战（多节点地图）。
- campaign/：战役（固定槽位编队）。
- exercise/：演习。
- decisive/：决战（独立阶段状态机，只把战斗交给引擎）。
- plan.py：战斗计划与节点决策（YAML 驱动）。
- plan_paths.py：计划文件定位。
- types.py：业务侧类型出口。
- fleet*.py：换船旧实现，待整体删除。

边界：不实现战斗主循环、阶段识别与点击；这些属于 application.combat。
"""

from importlib import import_module
from typing import TYPE_CHECKING

from autowsgr.business.combat.types import (
    ConditionFlag,
    FightCondition,
    FleetSelection,
    Formation,
    SearchEnemyAction,
)


if TYPE_CHECKING:
    from autowsgr.application.combat.history import (
        CombatResult,
        EventType,
        FightResult,
        grade_condition_met,
    )
    from autowsgr.application.combat.types import CombatMode
    from autowsgr.business.combat.plan import (
        CombatPlan,
        GradeCondition,
        NodeDecision,
        parse_map_value,
    )

_LAZY_EXPORTS: dict[str, str] = {
    'CombatMode': 'autowsgr.application.combat.types',
    'CombatPlan': 'autowsgr.business.combat.plan',
    'CombatResult': 'autowsgr.application.combat.history',
    'EventType': 'autowsgr.application.combat.history',
    'FightResult': 'autowsgr.application.combat.history',
    'GradeCondition': 'autowsgr.business.combat.plan',
    'NodeDecision': 'autowsgr.business.combat.plan',
    'grade_condition_met': 'autowsgr.application.combat.history',
    'parse_map_value': 'autowsgr.business.combat.plan',
}
"""按需加载的导出：模块路径 → 名字。避免包入口把整个编排层一起拖起来。"""


def __getattr__(name: str) -> object:
    """按需加载并缓存延迟导出。

    Args:
        name: 要访问的导出名。

    Returns:
        对应对象。

    Raises:
        AttributeError: 名字不在导出表里。
    """
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(module_path), name)
    globals()[name] = value
    return value


__all__ = [
    'CombatMode',
    'CombatPlan',
    'CombatResult',
    'ConditionFlag',
    'EventType',
    'FightCondition',
    'FightResult',
    'FleetSelection',
    'Formation',
    'GradeCondition',
    'NodeDecision',
    'SearchEnemyAction',
    'grade_condition_met',
    'parse_map_value',
]
