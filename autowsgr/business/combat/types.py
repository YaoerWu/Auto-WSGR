"""模块功能：战斗与舰队的业务侧类型出口。

战斗引擎使用的枚举（战况、阵型、索敌动作、战斗标记）定义在战斗引擎包内，这里
只做业务侧的统一出口，避免业务模块各自记引擎路径。舰船编队选项是业务概念，
留在本模块。

上层调用：
- business.combat.*：战斗计划、规则与各模式执行器。
- application.ui.controller.operations.sortie_page：决战页读取舰队选项。

边界：只放类型，不放行为。
"""

from __future__ import annotations

from dataclasses import dataclass

from autowsgr.application.combat.types import (
    ConditionFlag,
    FightCondition,
    Formation,
    SearchEnemyAction,
)


@dataclass
class FleetSelection:
    """战备舰队获取界面中单个可选项的信息。

    Attributes:
        name: 舰队名。
        cost: 消耗（如情报点）。
        click_position: 该项的相对点击坐标。
    """

    name: str
    cost: int
    click_position: tuple[float, float]


__all__ = [
    'ConditionFlag',
    'FightCondition',
    'FleetSelection',
    'Formation',
    'SearchEnemyAction',
]
