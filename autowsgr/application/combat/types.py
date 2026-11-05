"""模块功能：战斗模块的对外类型。

上层调用：
- application.combat 各子模块：判断阶段、选择阵型、解释战果。
- business.combat 编排层：选择战斗模式、读取战斗结果。

下层依赖：
- common.system.enums：项目统一的 IntEnum 与 StrEnum。
- application.controller.types：舰船血量与修理档位。

边界：只定义战斗领域的数据形状；不读写设备、不执行识别、不点击。
"""

from __future__ import annotations

from enum import auto
from typing import TYPE_CHECKING, Protocol

from autowsgr.application.controller.types import RepairMode, ShipDamageState
from autowsgr.common.system.enums import BaseEnum, IntEnum, StrEnum


if TYPE_CHECKING:
    from autowsgr.application.combat.engine.types import CombatPhase, PhaseBranch


class FightCondition(IntEnum):
    """战况选择（出征前）。"""

    steady_advance = 1
    firepower_forever = 2
    caution = 3
    aim = 4
    search_formation = 5

    @property
    def relative_click_position(self) -> tuple[float, float]:
        """对应的相对点击坐标（x, y）。"""
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


class CombatMode:
    """战斗模式标识。

    五种模式只在「多节点地图 / 单点」和「结束页面」上不同，状态转移图由
    ModeCategory 与结束页唯一确定，见 monitor/transitions.py。
    """

    NORMAL = 'normal'
    """常规战（多点地图）。"""

    BATTLE = 'battle'
    """战役（单点）。"""

    EXERCISE = 'exercise'
    """演习。"""

    DECISIVE = 'decisive'
    """决战（单点战斗，RESULT 即终止）。"""

    EVENT = 'event'
    """活动战斗（与常规战类似，但终止态为活动地图页面）。"""


class ModeCategory(BaseEnum):
    """战斗模式大类。

    所有具体 CombatMode 归入这两类之一，转移图由大类与结束页唯一确定。

    MAP
        多节点地图模式：有战况选择、迂回、导弹支援、舰船掉落、旗舰大破、
        继续前进 / 回港等完整流程（常规战、活动战）。
    SINGLE
        单点战斗模式：无多节点特性，只有核心战斗循环；结束页为空时
        以 RESULT 为终止态（战役、决战、演习）。
    """

    MAP = auto()
    SINGLE = auto()


class BattleNodeDecision(Protocol):
    """战斗引擎对节点决策的全部要求。

    编排层的节点决策对象只要具备这两个属性就能直接传入，引擎不 import 它的
    具体类型。
    """

    SL_when_enter_fight: bool
    """为真时进战斗前先尝试迂回躲避。"""

    night: bool
    """昼战结束后是否追击夜战。"""


class BattlePlan(Protocol):
    """战斗引擎对作战计划的全部要求。

    引擎只读这些成员，不构造、不修改计划；编排层按此形状传参即可，不需要
    import 本协议。转移图按「模式大类 + 结束页 + 采集开关」生成，见
    monitor/transitions.py。
    """

    mode: str
    """战斗模式，取值见 CombatMode。"""

    chapter: str
    """章节号。"""

    map_id: str
    """地图号。"""

    collect_result_info: bool
    """是否在战果页停留采集评级与 MVP。"""

    fight_condition: FightCondition
    """进图后选择的战况。"""

    @property
    def end_phase(self) -> CombatPhase:
        """战斗结束时停在哪个阶段。"""

    @property
    def transitions(self) -> dict[CombatPhase, PhaseBranch]:
        """本计划的阶段转移图。"""

    def is_selected_node(self, node: str) -> bool:
        """节点是否在允许推进的白名单里。"""

    def get_node_decision(self, node: str) -> BattleNodeDecision:
        """取该节点上的决策（是否迂回、是否夜战）。"""


__all__ = [
    'BattleNodeDecision',
    'BattlePlan',
    'CombatMode',
    'ConditionFlag',
    'FightCondition',
    'Formation',
    'ModeCategory',
    'RepairMode',
    'SearchEnemyAction',
    'ShipDamageState',
]
