"""模块功能：验证导航注册表的可达关系、页面分类与域探针。

直接调用方：项目测试运行器。

直接依赖：navigation.registry 与 controller 里的主页识别入口。

边界：只验证图上与登记表上的事实，不访问设备、不执行边动作。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from autowsgr.application.controller import home
from autowsgr.application.navigation import registry
from autowsgr.application.navigation.types import NavigationError, NavTarget, PageName


if TYPE_CHECKING:
    from collections.abc import Callable


def test_find_path_walks_from_home_to_registered_page() -> None:
    """起点即目标不需要动作；有路径时返回一串边，最后一条落在目标页。"""
    assert registry.find_path(PageName.HOME, PageName.HOME) == ()

    path = registry.find_path(PageName.HOME, PageName.MISSION)

    assert path
    assert all(isinstance(edge, NavTarget) for edge in path)
    assert path[-1].target is PageName.MISSION


def test_find_path_honors_exclusions_and_reports_unreachable() -> None:
    """排除某页后路径不再经过它；完全不可达时报带起止页面的导航错误。"""
    excluded = frozenset({PageName.HOME_NEWS})
    path = registry.find_path(PageName.HOME, PageName.MISSION, exclude=excluded)
    assert all(edge.target is not PageName.HOME_NEWS for edge in path)

    with pytest.raises(NavigationError, match='没有从'):
        registry.find_path(PageName.HOME, PageName.RANK_SKILL_LIST)


def test_depth_of_counts_hops_from_home() -> None:
    """主页深度为 0，可达页面等于最短跳数，不可达为负值。"""
    mission_path = registry.find_path(PageName.HOME, PageName.MISSION)

    assert registry.depth_of(PageName.HOME) == 0
    assert registry.depth_of(PageName.MISSION) == len(mission_path)
    assert registry.depth_of(PageName.RANK_SKILL_LIST) < 0


def test_registration_queries_expose_tabs_targets_and_checkers() -> None:
    """标签、出边与逐页入口都从同一张登记表查，未登记项给空值。"""
    tabs = registry.get_tabs(PageName.SORTIE_MAP)
    assert set(tabs) == {'sortie', 'exercise', 'expedition', 'campaign', 'decisive'}
    for tab in tabs.values():
        assert callable(tab.click)
        assert callable(tab.checker)
    assert registry.get_tabs(PageName.HOME) == {}

    targets = registry.get_targets(PageName.HOME)
    assert targets
    assert all(isinstance(edge, NavTarget) for edge in targets)
    assert registry.get_targets(PageName.RANK_SKILL_LIST) == ()

    entry: Callable[..., bool] | None = registry.get_checker(PageName.MISSION)
    assert callable(entry)
    assert registry.get_checker(PageName.HOME) is None
    assert registry.get_checker(PageName.RANK_SKILL_LIST) is None


def test_ship_pool_is_recognized_but_never_a_navigation_target() -> None:
    """船池页只做识别、不进导航图：怎么进、怎么退由决定进船池的模块自己接管。"""
    assert registry.get_checker(PageName.SHIP_SELECTION) is not None
    assert registry.get_targets(PageName.SHIP_SELECTION) == ()
    assert registry.depth_of(PageName.SHIP_SELECTION) < 0

    preparation_pages = (
        PageName.BATTLE_PREPARATION,
        PageName.DECISIVE_BATTLE_PREPARATION,
        PageName.EXERCISE_PREPARATION,
        PageName.CAMPAIGN_PREPARATION,
    )
    for page in preparation_pages:
        assert all(
            edge.target is not PageName.SHIP_SELECTION for edge in registry.get_targets(page)
        ), page
        with pytest.raises(NavigationError):
            registry.find_path(PageName.SHIP_SELECTION, page)


def test_page_classification_covers_overlays_domains_and_plain_pages() -> None:
    """浮窗、域页面与域的归属按登记表判定。"""
    assert registry.is_overlay_page(PageName.HOME_NEWS)
    assert not registry.is_overlay_page(PageName.HOME)

    assert registry.is_domain_page(PageName.HOME)
    assert registry.is_domain_page(PageName.BATTLE_PREPARATION)
    assert not registry.is_domain_page(PageName.MISSION)

    assert registry.domain_of(PageName.SORTIE_MAP) == registry.domain_of(PageName.EXERCISE)
    assert registry.domain_of(PageName.HOME) != registry.domain_of(PageName.SORTIE_MAP)
    assert registry.domain_of(PageName.MISSION) is None


def test_arrival_hooks_delegate_home_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗结算状态由主页识别模块唯一持有，且只有到主页才刷新标记。"""
    monkeypatch.setattr(home, 'popups_all_settled', lambda: True)
    marked: list[str] = []
    monkeypatch.setattr(home, 'mark_popups_settled', lambda _ctx: marked.append('home'))

    assert registry.popups_all_settled() is True

    registry.on_arrival(object(), PageName.HOME)
    registry.on_arrival(object(), PageName.SORTIE_MAP)

    assert marked == ['home']


def test_probe_domains_concatenates_every_prober(monkeypatch: pytest.MonkeyPatch) -> None:
    """域探针按登记顺序收集，返回元组，并把等待参数原样传下去。"""
    received: list[tuple[int, float]] = []

    def _first(_ctx: Any, *, attempts: int, interval_seconds: float) -> tuple[PageName, ...]:
        received.append((attempts, interval_seconds))
        return (PageName.HOME,)

    def _second(_ctx: Any, *, attempts: int, interval_seconds: float) -> tuple[PageName, ...]:
        received.append((attempts, interval_seconds))
        return ()

    monkeypatch.setattr(registry, '_DOMAIN_PROBERS', (_first, _second))

    assert registry.probe_domains(object(), attempts=2, interval_seconds=0.5) == (PageName.HOME,)
    assert received == [(2, 0.5), (2, 0.5)]
