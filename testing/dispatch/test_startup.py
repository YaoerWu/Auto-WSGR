"""模块功能：验证启动编排入口的分支与恢复。

直接调用方：项目测试运行器。

直接依赖：pytest、dispatch.startup、导航器错误类型与会话状态。

边界：用导航器与设备替身接管启动和导航，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.errors import ManualRepairRequiredError
from autowsgr.application.runtime.types import LoginServer
from autowsgr.application.navigation.types import (
    ManualUpdateRequiredError,
    NavigationError,
    PageName,
)
from autowsgr.dispatch import startup
from autowsgr.dispatch.session import SessionState


def _ctx(calls: list[str], *, running: bool, server: str = '默认') -> Any:
    """构造带设备与配置替身的上下文；设备动作记进 calls。"""
    # 拉起 App 之后进程就要变成"在跑"，否则等进程会一直忙等到超时。
    state = {'running': running}

    def _start_app(package: str) -> None:
        calls.append(f'start_app:{package}')
        state['running'] = True

    ctrl = SimpleNamespace(
        check_app_running=lambda _package: state['running'],
        start_app=_start_app,
        stop_app=lambda package: calls.append(f'stop_app:{package}'),
        follow_display=lambda package: calls.append(f'follow_display:{package}'),
    )
    account = SimpleNamespace(
        package_name='com.example.game',
        game_server=LoginServer(server),
    )
    runtime = SimpleNamespace(ctrl=ctrl, config=SimpleNamespace(account=account))
    return SimpleNamespace(runtime=runtime)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    navigate_error: Exception | None = None,
    session: SessionState | None = None,
) -> None:
    """用导航器替身接管启动与导航；导航错误只抛第一次。"""
    raised = {'done': False}

    class _Navigator:
        def __init__(self, _ctx: Any) -> None:
            pass

        def navigate_to_login(self) -> None:
            calls.append('navigate_to_login')

        def navigate_to(self, target: PageName, **params: object) -> None:
            calls.append(f'navigate_to:{target.value}')
            if 'server' in params:
                calls.append(f'server:{params["server"]}')
            if navigate_error is not None and not raised['done']:
                raised['done'] = True
                raise navigate_error

    monkeypatch.setattr(startup, 'NavigationService', _Navigator)
    monkeypatch.setattr(startup, 'get_session', lambda: session or SessionState())
    # 等进程与强杀后的等待对测试没有意义，直接置零。
    monkeypatch.setattr(startup, '_APP_PROCESS_POLL_SECONDS', 0.0)
    monkeypatch.setattr(startup, '_RESTART_SETTLE_SECONDS', 0.0)


def test_cold_start_launches_and_enters_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """冷启动：拉起 App、走启动段、按配置换区，最后回主页。"""
    calls: list[str] = []
    _install(monkeypatch, calls)

    startup.ensure_ready(_ctx(calls, running=False, server='胡德'))

    assert calls == [
        'start_app:com.example.game',
        'follow_display:com.example.game',
        'navigate_to_login',
        f'navigate_to:{PageName.SERVER_SELECT.value}',
        f'navigate_to:{PageName.LOGIN_PAGE.value}',
        'server:胡德',
        f'navigate_to:{PageName.HOME.value}',
    ]


def test_cold_start_clears_stale_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """游戏被重新拉起后必须清栈，否则回主页会被「已在目标页面」短路。"""
    calls: list[str] = []
    session = SessionState()
    session.push_page(PageName.HOME.value)
    _install(monkeypatch, calls, session=session)

    startup.ensure_ready(_ctx(calls, running=False, server='默认'))

    assert session.current_page() is None


def test_running_game_skips_startup_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """游戏在跑时不做启动段也不换区，直接回主页。"""
    calls: list[str] = []
    _install(monkeypatch, calls)

    startup.ensure_ready(_ctx(calls, running=True, server='胡德'))

    assert calls == [
        'follow_display:com.example.game',
        f'navigate_to:{PageName.HOME.value}',
    ]


def test_default_server_skips_region_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置为默认时不换区，启动段之后直接回主页。"""
    calls: list[str] = []
    _install(monkeypatch, calls)

    startup.ensure_ready(_ctx(calls, running=False, server='默认'))

    assert f'navigate_to:{PageName.SERVER_SELECT.value}' not in calls
    assert calls[-1] == f'navigate_to:{PageName.HOME.value}'


def test_update_required_becomes_manual_repair_without_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """需要更新时转成人工处理错误，且不触发 SL。"""
    calls: list[str] = []
    _install(monkeypatch, calls, navigate_error=ManualUpdateRequiredError('需要更新'))

    with pytest.raises(ManualRepairRequiredError, match='手动完成'):
        startup.ensure_ready(_ctx(calls, running=True))

    assert not any(call.startswith('stop_app') for call in calls)


def test_navigation_failure_restarts_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """导航失败时 SL 一次并重走初始化。"""
    calls: list[str] = []
    _install(monkeypatch, calls, navigate_error=NavigationError('识别不到页面'))

    startup.ensure_ready(_ctx(calls, running=True))

    assert 'stop_app:com.example.game' in calls
    assert calls.count(f'navigate_to:{PageName.HOME.value}') == 2


def test_restart_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """不允许 SL 时失败直接抛出，不做重启动作。"""
    calls: list[str] = []
    _install(monkeypatch, calls, navigate_error=NavigationError('识别不到页面'))

    with pytest.raises(NavigationError):
        startup.ensure_ready(_ctx(calls, running=True), allow_restart=False)

    assert not any(call.startswith('stop_app') for call in calls)
