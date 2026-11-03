"""模块功能：验证导航器入口的算路、回退与启动流程。

直接调用方：项目测试运行器。

直接依赖：navigation.service、navigation.registry 与 conftest 的替身。

边界：不连接设备；识别入口、路径执行与休眠全部用替身接管。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from autowsgr.application.navigation import registry
from autowsgr.application.navigation import service as service_module
from autowsgr.application.navigation.service import NavigationService
from autowsgr.application.navigation.types import (
    ManualUpdateRequiredError,
    NavigationError,
    PageName,
)


if TYPE_CHECKING:
    from autowsgr.dispatch.session import SessionState


def _service(
    ctx: Any,
    session: SessionState,
    *,
    forward: Any = None,
    backward: Any = None,
    layers: Any = None,
) -> NavigationService:
    """构造一个执行器已被替身接管的导航器。"""
    service = NavigationService(ctx, session=session, checkpoint=False)
    service._executor = SimpleNamespace(
        walk_forward=forward or (lambda _path, _params: None),
        walk_backward=backward or (lambda _path: None),
        read_layers_clearing_overlay=layers or (lambda: ()),
    )
    return service


def test_navigate_to_walks_from_current_page(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已在目标页不扫画面不算路；否则按当前页算路并把参数原样交给执行器。"""
    session.push_page(PageName.MISSION.value)
    monkeypatch.setattr(registry, 'find_path', lambda *_args, **_kwargs: pytest.fail('不应算路'))
    walked: list[object] = []
    service = _service(ctx, session, forward=lambda _path, _params: walked.append(_path))

    service.navigate_to(PageName.MISSION)
    assert walked == []

    session.clear_pages()
    session.push_page(PageName.HOME.value)
    path = (SimpleNamespace(target=PageName.MISSION),)
    received: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(registry, 'find_path', lambda _source, _target: path)
    service = _service(ctx, session, forward=lambda _path, params: received.append((_path, params)))

    service.navigate_to(PageName.MISSION, chapter=2)
    assert received == [(path, {'chapter': 2})]


def test_navigate_to_rebuilds_stack_when_current_page_unknown(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """栈空时先扫画面建栈；一层都没扫到就报错；清浮窗已记栈则不重复压栈。"""
    sources: list[PageName] = []
    monkeypatch.setattr(registry, 'find_path', lambda source, _target: sources.append(source) or ())
    service = _service(ctx, session, layers=lambda: (PageName.MISSION,))

    service.navigate_to(PageName.HOME)
    assert sources == [PageName.MISSION]
    assert session.current_page() == PageName.MISSION.value

    session.clear_pages()
    service = _service(ctx, session, layers=lambda: ())
    with pytest.raises(NavigationError, match='无法识别当前页面'):
        service.navigate_to(PageName.MISSION)

    session.clear_pages()

    def _layers() -> tuple[PageName, ...]:
        session.push_page(PageName.HOME.value)
        return (PageName.HOME,)

    service = _service(ctx, session, layers=_layers)
    service.navigate_to(PageName.MISSION)
    assert session.current_page() == PageName.HOME.value


def test_navigate_back_walks_to_previous_page(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空栈直接报错不识别；有上一页时按两页算路并让栈顶落回上一页。"""
    monkeypatch.setattr(registry, 'find_path', lambda *_args, **_kwargs: pytest.fail('不应算路'))
    service = _service(ctx, session, backward=lambda _path: pytest.fail('不应后退'))

    with pytest.raises(NavigationError, match='导航栈为空，无法回退'):
        service.navigate_back()

    session.push_page(PageName.HOME.value)
    session.push_page(PageName.MISSION.value)
    path = (SimpleNamespace(target=PageName.HOME),)
    walked: list[object] = []

    def _find_path(source: PageName, target: PageName) -> tuple[object, ...]:
        assert source is PageName.MISSION
        assert target is PageName.HOME
        return path

    monkeypatch.setattr(registry, 'find_path', _find_path)
    service = _service(ctx, session, backward=walked.append)

    service.navigate_back()
    assert walked == [path]
    assert session.current_page() == PageName.HOME.value


def test_navigate_back_restores_current_page_when_stack_has_only_it(
    ctx: Any,
    session: SessionState,
) -> None:
    """栈里只有当前页时，弹栈失败要把当前页放回去。"""
    session.push_page(PageName.HOME.value)
    service = _service(ctx, session)

    with pytest.raises(NavigationError, match='导航栈为空，无法回退'):
        service.navigate_back()

    assert session.current_page() == PageName.HOME.value


def test_navigate_to_login_clears_black_screen_then_waits_for_page(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """健康游戏提示要带 absent=True 等它消失；没有提示时先等一拍。"""
    black_calls: list[dict[str, object]] = []
    results = iter((True, False))
    monkeypatch.setattr(
        service_module.login,
        'check_black_screen',
        lambda _ctx, **options: black_calls.append(options) or next(results),
    )
    monkeypatch.setattr(service_module.login, 'check_update_prompt', lambda _ctx, **_options: False)
    monkeypatch.setattr(service_module.login, 'check_loading', lambda _ctx, **_options: False)
    monkeypatch.setattr(service_module.login, 'check_login_page', lambda _ctx, **_options: True)
    service = _service(ctx, session)

    service.navigate_to_login()
    assert black_calls == [{}, {'absent': True, 'attempts': 3, 'interval_seconds': 1.0}]

    slept: list[float] = []
    monkeypatch.setattr(service_module.time, 'sleep', slept.append)
    monkeypatch.setattr(service_module.login, 'check_black_screen', lambda _ctx, **_options: False)

    service.navigate_to_login()
    assert slept == [3.0]


def test_navigate_to_login_reports_manual_update_and_timeout(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """更新提示是硬分支；等不到登录页时报启动超时并带上等待参数。"""
    monkeypatch.setattr(service_module.login, 'check_black_screen', lambda _ctx, **_options: False)
    monkeypatch.setattr(service_module.login, 'check_update_prompt', lambda _ctx, **_options: True)
    monkeypatch.setattr(
        service_module.login,
        'check_login_page',
        lambda _ctx, **_options: pytest.fail('不应继续等登录页'),
    )
    service = _service(ctx, session)

    with pytest.raises(ManualUpdateRequiredError, match='检测到游戏更新'):
        service.navigate_to_login()

    login_calls: list[dict[str, object]] = []
    monkeypatch.setattr(service_module.login, 'check_update_prompt', lambda _ctx, **_options: False)
    monkeypatch.setattr(service_module.login, 'check_loading', lambda _ctx, **_options: False)
    monkeypatch.setattr(
        service_module.login,
        'check_login_page',
        lambda _ctx, **options: login_calls.append(options) or False,
    )

    with pytest.raises(NavigationError, match='启动超时'):
        service.navigate_to_login()

    assert login_calls == [{'attempts': 60, 'interval_seconds': 1.0}]


def test_current_page_leaves_ship_pool_before_rebuilding_stack(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空栈停在船池页：先退一步，再按重新识别到的准备页建栈。"""
    scans = iter([(PageName.SHIP_SELECTION,), (PageName.BATTLE_PREPARATION,)])
    service = _service(ctx, session, layers=lambda: next(scans))
    backed: list[bool] = []
    monkeypatch.setattr(
        service_module,
        'ShipPoolPage',
        lambda _ctx: SimpleNamespace(go_back=lambda: backed.append(True)),
    )

    assert service._current_page() is PageName.BATTLE_PREPARATION
    assert backed == [True]
    assert session.current_page() == PageName.BATTLE_PREPARATION.value


def test_current_page_gives_up_when_ship_pool_cannot_be_left(
    ctx: Any,
    session: SessionState,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退出之后还停在船池页：不硬猜路径，直接报无法识别。"""
    scans = iter([(PageName.SHIP_SELECTION,)] * 3)
    service = _service(ctx, session, layers=lambda: next(scans))
    monkeypatch.setattr(
        service_module,
        'ShipPoolPage',
        lambda _ctx: SimpleNamespace(go_back=lambda: None),
    )

    with pytest.raises(NavigationError):
        service._current_page()
