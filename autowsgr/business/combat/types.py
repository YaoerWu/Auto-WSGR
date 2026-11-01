"""战斗与舰队领域类型。"""

from __future__ import annotations

from dataclasses import dataclass

from autowsgr.common.system.enums import IntEnum, StrEnum


class FightCondition(IntEnum):
    """战况选择（出征前）。"""

    steady_advance = 1
    firepower_forever = 2
    caution = 3
    aim = 4
    search_formation = 5

    @property
    def relative_click_position(self) -> tuple[float, float]:
        """对应的相对点击坐标 (x, y)。"""
        positions: dict[int, tuple[float, float]] = {
            1: (0.215, 0.409),
            2: (0.461, 0.531),
            3: (0.783, 0.362),
            4: (0.198, 0.764),
            5: (0.763, 0.740),
        }
        return positions[self.value]


class Formation(IntEnum):
    """阵型选择。"""

    single_column = 1
    double_column = 2
    circular = 3
    wedge = 4
    single_horizontal = 5

    @property
    def relative_position(self) -> tuple[float, float]:
        """阵型按钮的相对位置。"""
        return 0.597, self.value * 0.185 - 0.037


@dataclass
class FleetSelection:
    """战备舰队获取界面中单个可选项的信息。"""

    name: str
    cost: int
    click_position: tuple[float, float]


class SearchEnemyAction(StrEnum):
    """索敌后可执行的动作。"""

    no_action = 'no_action'
    retreat = 'retreat'
    detour = 'detour'
    refresh = 'refresh'


class ConditionFlag(StrEnum):
    """战斗流程状态标记。"""

    DOCK_FULL = 'dock is full'
    FIGHT_END = 'fight end'
    FIGHT_CONTINUE = 'fight continue'
    OPERATION_SUCCESS = 'success'
    BATTLE_TIMES_EXCEED = 'out of times'
    SKIP_FIGHT = 'skip fight'
    SL = 'SL'
    ACTION_FAILED = 'action failed'
