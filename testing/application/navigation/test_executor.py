"""模块功能：验证导航执行器的逐边执行、到达确认与栈记账流程。

直接调用方：项目测试运行器。
直接依赖：navigation.executor、navigation.registry 与 conftest 的替身。
边界：不识别画面、不连接设备；页面确认与层扫描全部用替身接管。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from autowsgr.application.navigation import registry
from autowsgr.application.navigation.executor import NavigationExecutor
from autowsgr.application.navigation.types import NavigationError, NavTab, NavTarget, PageName


if TYPE_CHECKING:
    from autowsgr.dispatch.session import SessionState


def _edge(
    target: PageName,
    *,
    calls: list[str] | None = None,
    confirm: bool = True,
    tab: str | None = None,
) -> NavTarget:
    """构造一条记录调用顺序的测试边。"""

    def _action(_ctx: Any, **_params: object) -> None:
        if calls is not None:
            calls.append(target.value)

    return NavTarget(target, _action, description='测试边', confirm=confirm, tab=tab)


def _skip_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """跳过到达确认，只观察动作、栈与标签。"""
    monkeypatch.setattr(NavigationExecutor, '_confirm_arrival', lambda _self, _edge: None)


def _accept_page(monkeypatch: pytest.MonkeyPatch, target: PageName) -> None:
    """让某一页的逐页确认命中，并让层扫描只报出这一页。"""
    monkeypatch.setattr(registry, 'is_domain_page', lambda _page: False)
    monkeypatch.setitem(registry._PAGE_CHECKERS, target, lambda _ctx, **_options: True)
    monkeypatch.setattr(NavigationExecutor, 'detect_layer', lambda _self, **_options: (target,))


def test_walk_forward_records_each_arrival_while_backward_leaves_stack_alone(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """前进按顺序执行动作、透传参数并逐页记栈；confirm=False 的边不确认但仍记栈；后退不动栈。"""
    calls: list[str] = []
    received: list[dict[str, object]] = []

    def _capture(_ctx: Any, **params: object) -> None:
        received.append(params)

    path = (
        _edge(PageName.MISSION, calls=calls),
        NavTarget(PageName.BACKYARD, _capture, description='带参数边'),
    )
    _skip_confirm(monkeypatch)

    NavigationExecutor(ctx, session).walk_forward(path, {'chapter': 3, 'tab': 5})

    assert calls == [PageName.MISSION.value]
    assert received == [{'chapter': 3, 'tab': 5}]
    assert session.current_page() == PageName.BACKYARD.value

    monkeypatch.setitem(
        registry._PAGE_CHECKERS,
        PageName.MISSION,
        lambda _ctx, **_options: (_ for _ in ()).throw(AssertionError('不应确认')),
    )
    NavigationExecutor(ctx, session).walk_forward((_edge(PageName.MISSION, confirm=False),), {})
    assert session.pop_page() == PageName.MISSION.value

    back: list[str] = []
    NavigationExecutor(ctx, session).walk_backward((_edge(PageName.HOME, calls=back),))

    assert back == [PageName.HOME.value]
    assert session.current_page() == PageName.BACKYARD.value


def test_walk_forward_enters_tabs_on_their_own_edges(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中间跳用边自己的标签、最后一跳用调用方参数；未知标签与切换失败都报错。"""
    clicked: list[str] = []
    monkeypatch.setitem(
        registry._TABS,
        PageName.EXERCISE,
        {'exercise': NavTab(lambda _ctx: clicked.append('exercise'), lambda _ctx: True, '演习')},
    )
    monkeypatch.setitem(
        registry._TABS,
        PageName.SORTIE_MAP,
        {'sortie': NavTab(lambda _ctx: clicked.append('sortie'), lambda _ctx: True, '出征')},
    )
    _skip_confirm(monkeypatch)

    path = (_edge(PageName.EXERCISE, tab='exercise'), _edge(PageName.SORTIE_MAP))
    NavigationExecutor(ctx, session).walk_forward(path, {'tab': 'sortie'})
    assert clicked == ['exercise', 'sortie']

    monkeypatch.setitem(registry._TABS, PageName.SORTIE_MAP, {})
    with pytest.raises(NavigationError, match='没有标签'):
        NavigationExecutor(ctx, session).walk_forward((_edge(PageName.SORTIE_MAP),), {'tab': 'x'})

    retried: list[str] = []
    monkeypatch.setitem(
        registry._TABS,
        PageName.SORTIE_MAP,
        {'sortie': NavTab(lambda _ctx: retried.append('sortie'), lambda _ctx: False, '出征')},
    )
    with pytest.raises(NavigationError, match='标签切换失败'):
        NavigationExecutor(ctx, session).walk_forward(
            (_edge(PageName.SORTIE_MAP),),
            {'tab': 'sortie'},
        )
    assert retried == ['sortie', 'sortie']


def test_arrival_rejects_unconfirmed_or_covered_target(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目标页确认不通过、被更深层盖住或域探针不符都算未到达。"""
    monkeypatch.setitem(registry._PAGE_CHECKERS, PageName.MISSION, lambda _ctx, **_options: False)
    monkeypatch.setattr(NavigationExecutor, 'detect_layer', lambda _self, **_options: ())
    with pytest.raises(NavigationError, match='到达确认失败'):
        NavigationExecutor(ctx, session).walk_forward((_edge(PageName.MISSION),), {})
    assert session.current_page() is None

    _accept_page(monkeypatch, PageName.MISSION)
    monkeypatch.setattr(
        NavigationExecutor,
        'detect_layer',
        lambda _self, **_options: (PageName.SIDEBAR, PageName.MISSION),
    )
    with pytest.raises(NavigationError, match='当前层是'):
        NavigationExecutor(ctx, session).walk_forward((_edge(PageName.MISSION),), {})

    monkeypatch.setattr(registry, 'is_domain_page', lambda _page: True)
    monkeypatch.setattr(registry, 'probe_domains', lambda _ctx, **_options: (PageName.HOME,))
    with pytest.raises(NavigationError, match='当前层是'):
        NavigationExecutor(ctx, session).walk_forward((_edge(PageName.SORTIE_MAP),), {})

    monkeypatch.setattr(registry, 'probe_domains', lambda _ctx, **_options: ())
    with pytest.raises(NavigationError, match='未识别到任何页面'):
        NavigationExecutor(ctx, session).walk_forward((_edge(PageName.SORTIE_MAP),), {})


def test_arrival_notifies_registry_for_page_and_domain(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """逐页确认命中或域探针命中后都通知注册表，再记栈。"""
    arrivals: list[PageName] = []
    _accept_page(monkeypatch, PageName.MISSION)
    monkeypatch.setattr(registry, 'on_arrival', lambda _ctx, page: arrivals.append(page))

    NavigationExecutor(ctx, session).walk_forward((_edge(PageName.MISSION),), {})
    assert arrivals == [PageName.MISSION]
    assert session.current_page() == PageName.MISSION.value

    monkeypatch.setattr(registry, 'is_domain_page', lambda _page: True)
    monkeypatch.setattr(
        registry,
        'probe_domains',
        lambda _ctx, **_options: (PageName.SORTIE_MAP, PageName.EXERCISE),
    )
    NavigationExecutor(ctx, session).walk_forward((_edge(PageName.SORTIE_MAP),), {})
    assert arrivals == [PageName.MISSION, PageName.SORTIE_MAP]


def test_checkpoint_is_queried_around_each_edge(
    ctx: Any,
    session: SessionState,
    checkpoint: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每跳前后各过一次断点，收尾那趟关掉断点时不查询。"""
    _skip_confirm(monkeypatch)

    NavigationExecutor(ctx, session).walk_forward((_edge(PageName.MISSION),), {})
    assert checkpoint.calls == 2

    checkpoint.error = RuntimeError('收到终止信号')
    NavigationExecutor(ctx, session, checkpoint=False).walk_forward(
        (_edge(PageName.MISSION),),
        {},
    )
    assert checkpoint.calls == 2


def test_record_page_keeps_one_entry_per_domain(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """浮窗不占栈，同域换页只替换栈顶，跨域才压新的一格。"""
    executor = NavigationExecutor(ctx, session)
    monkeypatch.setattr(registry, 'is_overlay_page', lambda _page: True)
    executor._record_page(PageName.HOME_NEWS)
    assert session.current_page() is None

    monkeypatch.setattr(registry, 'is_overlay_page', lambda _page: False)
    monkeypatch.setattr(registry, 'domain_of', lambda _page: 0)
    session.push_page(PageName.HOME.value)
    executor._record_page(PageName.HOME_NEWS)
    assert session.current_page() == PageName.HOME_NEWS.value

    monkeypatch.setattr(registry, 'domain_of', lambda page: 0 if page is PageName.HOME else 1)
    session.push_page(PageName.HOME.value)
    executor._record_page(PageName.SORTIE_MAP)
    assert session.current_page() == PageName.SORTIE_MAP.value
    assert session.pop_page() == PageName.SORTIE_MAP.value


def test_detect_layer_orders_hits_and_ignores_failing_checkers(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """命中多层按深度降序返回，确认入口报错按不匹配处理。"""
    hits = {PageName.HOME, PageName.MISSION}
    monkeypatch.setattr(registry, 'probe_domains', lambda _ctx, **_options: ())
    monkeypatch.setattr(
        registry,
        'get_checker',
        lambda page: (lambda _ctx, **_options: page in hits) if page in hits else None,
    )
    monkeypatch.setattr(registry, 'depth_of', lambda page: 3 if page is PageName.MISSION else 0)

    executor = NavigationExecutor(ctx, session)
    assert executor.detect_layer() == (PageName.MISSION, PageName.HOME)

    def _boom(_ctx: Any, **_options: object) -> bool:
        raise RuntimeError('缺少活动参数')

    monkeypatch.setattr(
        registry, 'get_checker', lambda page: _boom if page is PageName.EVENT_MAP else None
    )
    assert executor.detect_layer() == ()


def test_read_layers_clearing_overlay_walks_to_underlying_page(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """停在浮窗上时先走回它盖住的页面，正常画面则直接返回。"""
    layers = iter(((PageName.HOME_NEWS, PageName.HOME), (PageName.HOME,)))
    walked: list[tuple[Any, dict[str, object]]] = []
    executor = NavigationExecutor(ctx, session)
    monkeypatch.setattr(executor, 'detect_layer', lambda **_options: next(layers))
    monkeypatch.setattr(registry, 'is_overlay_page', lambda page: page is PageName.HOME_NEWS)
    monkeypatch.setattr(registry, 'find_path', lambda _source, _target: ())
    monkeypatch.setattr(
        executor, 'walk_forward', lambda path, params: walked.append((path, params))
    )

    assert executor.read_layers_clearing_overlay() == (PageName.HOME,)
    assert walked == [((), {})]

    plain = NavigationExecutor(ctx, session)
    monkeypatch.setattr(plain, 'detect_layer', lambda **_options: (PageName.MISSION,))
    monkeypatch.setattr(registry, 'is_overlay_page', lambda _page: False)
    assert plain.read_layers_clearing_overlay() == (PageName.MISSION,)
