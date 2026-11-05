"""模块功能：战斗阶段枚举。

上层调用：
- controller.sortie.battle_engine.monitor.constants：为每个阶段登记视觉判据。
- controller.sortie.battle_engine.monitor.checker：返回识别到的阶段。
- application.combat.engine：状态机流转与阶段分派。

下层依赖：
- common.system.enums：BaseEnum 基类。

边界：只定义阶段枚举；不持有运行时状态、不读写设备。
"""

from __future__ import annotations

from enum import auto

from autowsgr.common.system.enums import BaseEnum


__all__ = [
    'CombatPhase',
]


class CombatPhase(BaseEnum):
    """战斗阶段。

    每个枚举值代表战斗状态机中的一个离散状态。
    """

    # ── 出征过渡 ──
    START_FIGHT = auto()
    """点击出征后的短暂过渡：检测船坞已满或进入战斗。"""

    # ── 船坞已满 ──
    DOCK_FULL = auto()
    """出征时检测到船坞已满弹窗。"""

    # ── 航行 / 继续 ──
    PROCEED = auto()
    """继续前进 / 回港提示。"""

    # ── 战况选择 ──
    FIGHT_CONDITION = auto()
    """战况选择界面（稳步前进 / 火力万岁等）。"""

    # ── 索敌 ──
    SPOT_ENEMY_SUCCESS = auto()
    """索敌成功，显示敌方编成。"""

    # ── 阵型选择 ──
    FORMATION = auto()
    """选择阵型界面。"""

    # ── 导弹支援 ──
    MISSILE_ANIMATION = auto()
    """导弹支援动画播放中。"""

    # ── 战斗进行 ──
    FIGHT_PERIOD = auto()
    """昼战 / 夜战战斗动画进行中。"""

    # ── 夜战提示 ──
    NIGHT_PROMPT = auto()
    """夜战选择提示（追击 / 撤退）。"""

    # ── 战果结算 ──
    RESULT = auto()
    """战果评价界面（S/A/B/C/D/SS）。"""

    EXP_SETTLEMENT = auto()
    """经验结算子页（战果页点击后，逐舰船显示经验增加）。"""

    # ── 掉落 ──
    GET_SHIP = auto()
    """获取舰船掉落。"""

    # ── 旗舰大破 ──
    FLAGSHIP_SEVERE_DAMAGE = auto()
    """旗舰大破强制回港。"""

    # ── 结束页面 ──
    MAP_PAGE = auto()
    """回到地图页面（常规战结束）。"""

    EXERCISE_PAGE = auto()
    """回到演习页面（演习结束）。"""

    EVENT_MAP_PAGE = auto()
    """回到活动地图页面（活动战斗结束）。"""
