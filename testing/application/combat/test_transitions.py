"""模块功能：验证五种战斗模式的转移图与后继解析。

直接调用方：pytest。

直接依赖：application.combat.engine.transitions 与 types。

边界：只跑纯数据断言，不连设备、不读截图、不读模板文件。
"""

from __future__ import annotations

from autowsgr.application.combat.engine.transitions import (
    MODE_CATEGORIES,
    MODE_END_PHASES,
    MODE_SPECS,
    build_transitions,
    resolve_successors,
)
from autowsgr.application.combat.engine.types import CombatPhase
from autowsgr.application.combat.types import CombatMode, ModeCategory


EXPECTED_SPECS = {
    CombatMode.NORMAL: (ModeCategory.MAP, CombatPhase.MAP_PAGE),
    CombatMode.EVENT: (ModeCategory.MAP, CombatPhase.EVENT_MAP_PAGE),
    CombatMode.BATTLE: (ModeCategory.SINGLE, None),
    CombatMode.DECISIVE: (ModeCategory.SINGLE, None),
    CombatMode.EXERCISE: (ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE),
}
"""五种模式只由「大类 + 结束页」两个参数区分，这是引擎能不带模式分支的前提。"""


def test_mode_specs_cover_every_mode() -> None:
    """五种模式都必须登记，且大类与结束页固定。"""
    assert MODE_SPECS == EXPECTED_SPECS


def test_end_phase_falls_back_to_result_for_single_point_battles() -> None:
    """没有独立结束页的模式（战役 / 决战）以战果页为终点。"""
    assert MODE_END_PHASES[CombatMode.NORMAL] is CombatPhase.MAP_PAGE
    assert MODE_END_PHASES[CombatMode.BATTLE] is CombatPhase.RESULT
    assert MODE_END_PHASES[CombatMode.DECISIVE] is CombatPhase.RESULT
    assert MODE_END_PHASES[CombatMode.EXERCISE] is CombatPhase.EXERCISE_PAGE
    assert set(MODE_CATEGORIES) == set(EXPECTED_SPECS)


def test_map_graph_routes_through_map_pages() -> None:
    """MAP 类要经过地图路由阶段，SINGLE 类不该出现这些阶段。"""
    map_graph = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)
    single_graph = build_transitions(ModeCategory.SINGLE, None)

    for phase in (CombatPhase.PROCEED, CombatPhase.FIGHT_CONDITION):
        assert phase in map_graph
        assert phase not in single_graph


def test_single_graph_ends_at_its_own_end_page() -> None:
    """SINGLE 类收尾：战果页停在经验结算，经验页直接回结束页。"""
    graph = build_transitions(ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE)

    assert graph[CombatPhase.RESULT] == [CombatPhase.EXP_SETTLEMENT]
    assert graph[CombatPhase.EXP_SETTLEMENT] == [CombatPhase.EXERCISE_PAGE]


def test_result_page_waits_for_exp_settlement_only_when_collecting() -> None:
    """慢速采集时战果页必须先进经验页；快速穿行才允许直接跳结束。"""
    slow = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE, collect_result_info=True)
    fast = build_transitions(
        ModeCategory.MAP,
        CombatPhase.MAP_PAGE,
        collect_result_info=False,
    )

    assert slow[CombatPhase.RESULT] == [CombatPhase.EXP_SETTLEMENT]
    assert CombatPhase.EXP_SETTLEMENT not in fast[CombatPhase.RESULT]
    assert CombatPhase.PROCEED in fast[CombatPhase.RESULT]


def test_build_transitions_is_cached() -> None:
    """同一组参数只构建一次，计划属性反复访问不会重建整张图。"""
    first = build_transitions(ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE)
    second = build_transitions(ModeCategory.SINGLE, CombatPhase.EXERCISE_PAGE)
    other = build_transitions(
        ModeCategory.SINGLE,
        CombatPhase.EXERCISE_PAGE,
        collect_result_info=False,
    )

    assert first is second
    assert other is not first


def test_resolve_successors_follows_action_branch() -> None:
    """按动作名选分支；动作不认识时退回第一个分支。"""
    graph = build_transitions(ModeCategory.MAP, CombatPhase.MAP_PAGE)

    detour = resolve_successors(graph, CombatPhase.SPOT_ENEMY_SUCCESS, 'detour')
    fight = resolve_successors(graph, CombatPhase.SPOT_ENEMY_SUCCESS, 'fight')
    unknown = resolve_successors(graph, CombatPhase.SPOT_ENEMY_SUCCESS, 'unexpected')

    assert set(detour) == {
        CombatPhase.FIGHT_CONDITION,
        CombatPhase.SPOT_ENEMY_SUCCESS,
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
    }
    assert set(fight) == {
        CombatPhase.FORMATION,
        CombatPhase.FIGHT_PERIOD,
        CombatPhase.MISSILE_ANIMATION,
    }
    assert unknown == fight
