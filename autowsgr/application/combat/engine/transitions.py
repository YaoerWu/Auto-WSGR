"""模块功能：战斗状态转移图。

一次完整的 MAP 类战斗流程：

    PROCEED → FIGHT_CONDITION → SPOT_ENEMY_SUCCESS → FORMATION
        → FIGHT_PERIOD → NIGHT_PROMPT → RESULT → EXP_SETTLEMENT
        → GET_SHIP → PROCEED → ...

上层调用：
- application.combat.engine.loop：取当前模式的转移图驱动主循环。
- application.combat.plan：按模式取结束页。

下层依赖：
- application.combat.types：CombatMode、ModeCategory。
- application.combat.engine.types：CombatPhase、PhaseBranch。

边界：只描述阶段之间的合法流转；不读写设备、不点击、不保存运行时状态。
"""

from __future__ import annotations

from functools import cache

from autowsgr.application.combat.engine.types import CombatPhase, PhaseBranch
from autowsgr.application.combat.types import CombatMode, ModeCategory


__all__ = [
    'MODE_CATEGORIES',
    'MODE_END_PHASES',
    'MODE_SPECS',
    'ModeSpec',
    'build_transitions',
    'resolve_successors',
]


def build_transitions(
    category: ModeCategory,
    end_page: CombatPhase | None,
    *,
    collect_result_info: bool = True,
) -> dict[CombatPhase, PhaseBranch]:
    """根据模式大类和结束页面自动构建状态转移图。

    参数：
        category: MAP 或 SINGLE。
        end_page: 战斗结束游戏回到的页面状态；None 表示以 RESULT 作为终止态。
        collect_result_info: 是否在战果页停留采集评级 / MVP（慢速通过）。为 True（默认）
            时经验结算页进入状态机，处理器在 RESULT 页完成信息采集后再逐页推进；
            显式传入 False 才启用快速穿行兼容路径。

    返回：
        dict[CombatPhase, PhaseBranch]，阶段到后继的映射。返回值按
        (大类, 结束页, 采集开关) 缓存，**多个调用方拿到的是同一份 dict，只读**。
    """
    return _cached_transitions(category, end_page, collect_result_info)


@cache
def _cached_transitions(
    category: ModeCategory,
    end_page: CombatPhase | None,
    collect_result_info: bool,
) -> dict[CombatPhase, PhaseBranch]:
    """构建并按参数缓存转移图，避免每次访问计划属性都重建一次。"""
    if category == ModeCategory.MAP:
        return _build_map_transitions(end_page, collect_result_info)
    return _build_single_transitions(end_page, collect_result_info)


def _build_map_transitions(
    end_page: CombatPhase | None,
    collect_result_info: bool = True,
) -> dict[CombatPhase, PhaseBranch]:
    """MAP 类：多节点地图战斗的完整转移图。"""
    ep = end_page
    t: dict[CombatPhase, PhaseBranch] = {}

    # 地图移动后的着陆节点
    core_nav = [
        CombatPhase.FIGHT_CONDITION,
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    fight_targets = [
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    ]

    # RESULT 之后
    after_result = [CombatPhase.PROCEED]
    if ep is not None:
        after_result.append(ep)
    after_result += [CombatPhase.GET_SHIP, CombatPhase.FLAGSHIP_SEVERE_DAMAGE]

    # ── 各节点 ──
    start = list(core_nav)
    if ep is not None:
        start.append(ep)
    start.append(CombatPhase.DOCK_FULL)
    t[CombatPhase.START_FIGHT] = start

    t[CombatPhase.DOCK_FULL] = []

    proceed_yes = list(core_nav)
    if ep is not None:
        proceed_yes.append(ep)
    t[CombatPhase.PROCEED] = {
        'yes': proceed_yes,
        'no': [ep] if ep is not None else [],
    }

    t[CombatPhase.FIGHT_CONDITION] = [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    t[CombatPhase.SPOT_ENEMY_SUCCESS] = {
        'fight': list(fight_targets),
        'detour': list(core_nav),
        'retreat': [ep] if ep is not None else [],
    }

    t[CombatPhase.FORMATION] = [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    ]

    t[CombatPhase.MISSILE_ANIMATION] = [
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.RESULT,
    ]

    t[CombatPhase.FIGHT_PERIOD] = [CombatPhase.NIGHT_PROMPT, CombatPhase.RESULT]
    t[CombatPhase.NIGHT_PROMPT] = {
        'yes': [CombatPhase.RESULT],
        'no': [CombatPhase.RESULT],
    }

    # 战果页点击后必进经验结算子页（游戏固定流转），掉落 / 继续前进等只能从经验页到达。
    # 默认慢速模式进入状态机逐页采集 grade/MVP；仅显式传入 False 时才快速穿行。
    if collect_result_info:
        t[CombatPhase.RESULT] = [CombatPhase.EXP_SETTLEMENT]
    else:
        t[CombatPhase.RESULT] = list(after_result)
    t[CombatPhase.EXP_SETTLEMENT] = list(after_result)

    # GET_SHIP 后继 = 经验结算后继去掉 GET_SHIP 自身
    t[CombatPhase.GET_SHIP] = [p for p in after_result if p != CombatPhase.GET_SHIP]

    if ep is not None:
        t[CombatPhase.FLAGSHIP_SEVERE_DAMAGE] = [ep]

    return t


def _build_single_transitions(
    end_page: CombatPhase | None,
    collect_result_info: bool = True,
) -> dict[CombatPhase, PhaseBranch]:
    """SINGLE 类：单点战斗的精简转移图。"""
    ep = end_page
    t: dict[CombatPhase, PhaseBranch] = {}

    core = [
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    ]

    t[CombatPhase.START_FIGHT] = [*list(core), CombatPhase.DOCK_FULL]
    t[CombatPhase.DOCK_FULL] = []

    t[CombatPhase.SPOT_ENEMY_SUCCESS] = {
        'fight': [CombatPhase.FORMATION, CombatPhase.FIGHT_PERIOD],
        'retreat': [ep] if ep is not None else [],
    }

    t[CombatPhase.FORMATION] = [CombatPhase.FIGHT_PERIOD]
    t[CombatPhase.FIGHT_PERIOD] = [CombatPhase.NIGHT_PROMPT, CombatPhase.RESULT]
    t[CombatPhase.NIGHT_PROMPT] = {
        'yes': [CombatPhase.RESULT],
        'no': [CombatPhase.RESULT],
    }

    if ep is not None:
        # 演习等：默认慢速逐页（战果 → 经验 → 结束），显式 False 时快速穿行
        if collect_result_info:
            t[CombatPhase.RESULT] = [CombatPhase.EXP_SETTLEMENT]
            t[CombatPhase.EXP_SETTLEMENT] = [ep]
        else:
            t[CombatPhase.RESULT] = [ep]
            t[CombatPhase.EXP_SETTLEMENT] = [ep]
    else:
        # ep is None（战役 / 决战）→ RESULT 为终止态；引擎在 RESULT 即返回，
        # 经验页由 _click_result_until_closed 的候选集合兜住，无转移后继。
        t[CombatPhase.EXP_SETTLEMENT] = []

    return t


def resolve_successors(
    transitions: dict[CombatPhase, PhaseBranch],
    phase: CombatPhase,
    last_action: str,
) -> list[CombatPhase]:
    """根据当前状态和上一步动作，解析出候选后继状态列表。

    参数：
        transitions: 状态转移图。
        phase: 当前状态。
        last_action: 上一步动作名称，用于按动作分支的后继。

    返回：
        候选后继阶段列表。

    异常：
        KeyError: 当前状态不在转移图中。
    """
    branch = transitions[phase]

    if isinstance(branch, dict):
        targets = branch.get(last_action)
        if targets is None:
            targets = next(iter(branch.values()))
    else:
        targets = branch

    return list(targets)


# ── 模式配置 ── 每种战斗模式只需指定大类和结束页 ──────────────

ModeSpec = tuple[ModeCategory, CombatPhase | None]
"""模式规格：(大类, 结束页面)。None 的 end_page 表示 RESULT 即终止。"""

MODE_SPECS: dict[str, ModeSpec] = {
    CombatMode.NORMAL: (ModeCategory.MAP, CombatPhase.MAP_PAGE),
    CombatMode.EVENT: (ModeCategory.MAP, CombatPhase.EVENT_MAP_PAGE),
    CombatMode.BATTLE: (ModeCategory.SINGLE, None),
    CombatMode.DECISIVE: (ModeCategory.SINGLE, None),
    CombatMode.EXERCISE: (ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE),
}

MODE_END_PHASES: dict[str, CombatPhase] = {
    mode: (ep if ep is not None else CombatPhase.RESULT) for mode, (_cat, ep) in MODE_SPECS.items()
}
"""各模式判定为结束的阶段。"""

MODE_CATEGORIES: dict[str, ModeCategory] = {mode: cat for mode, (cat, _ep) in MODE_SPECS.items()}
"""各模式的战斗大类。"""
