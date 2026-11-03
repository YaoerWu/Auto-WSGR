"""模块功能：导航器单测的共享替身。

直接调用方：testing/application/navigation 下的各测试模块。

直接依赖：pytest、navigation 的注册表与 controller 里的识别入口。

边界：用替身接管设备点击与页面确认，不连接设备、不识别画面。
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from autowsgr.application.controller import home, login, sidebar
from autowsgr.application.navigation import registry
from autowsgr.application.navigation.types import NavTab, PageName
from autowsgr.dispatch.session import SessionState


if TYPE_CHECKING:
    from collections.abc import Callable


class FakeControl:
    """设备服务替身，记录点击与滑动落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []
        self.swipes: list[tuple[float, ...]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))

    def swipe(self, *positions: float) -> None:
        self.swipes.append(positions)


class FakeCheckpoint:
    """断点替身，记录被查询的次数，可按需抛出。"""

    def __init__(self) -> None:
        self.calls = 0
        self.error: BaseException | None = None

    def __call__(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


@pytest.fixture(autouse=True)
def _silence_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """导航里的稳定等待对单测没有意义，统一跳过，避免测试变慢。"""
    monkeypatch.setattr(time, 'sleep', lambda _seconds: None)


@pytest.fixture
def control() -> FakeControl:
    """设备服务替身。"""
    return FakeControl()


@pytest.fixture
def checkpoint() -> FakeCheckpoint:
    """断点替身。"""
    return FakeCheckpoint()


@pytest.fixture
def ctx(control: FakeControl, checkpoint: FakeCheckpoint) -> Any:
    """带设备替身与断点替身的上下文。"""
    return SimpleNamespace(
        runtime=SimpleNamespace(ctrl=control),
        check_interrupt=checkpoint,
        record_screenshot=lambda _frame: None,
    )


@pytest.fixture
def session() -> SessionState:
    """空的导航会话状态。"""
    return SessionState()


@pytest.fixture
def accept_path(monkeypatch: pytest.MonkeyPatch) -> Callable[[PageName], None]:
    """返回「只让目标页的确认入口命中」的安装器。

    替身跟着 absent 翻转：后识别问的是「这一页还在不在」，从更深的层退回时
    出发页必须判为已经收起。链路上 confirm=False 的中间步不做到达确认，
    因此只需要最终目标命中。
    """

    def _install(target: PageName) -> None:
        for page in list(registry._PAGE_CHECKERS):
            matched = page is target
            monkeypatch.setitem(
                registry._PAGE_CHECKERS,
                page,
                lambda _ctx, *, absent=False, _matched=matched, **_kwargs: _matched != absent,
            )
        if registry.is_domain_page(target):
            monkeypatch.setattr(
                registry,
                '_DOMAIN_PROBERS',
                (lambda _ctx, **_options: (target,),),
            )
        else:
            monkeypatch.setattr(registry, '_DOMAIN_PROBERS', (lambda _ctx, **_options: (),))
        monkeypatch.setattr(
            home,
            'read_news_overlay',
            lambda _ctx: SimpleNamespace(matched=False, checked=None),
        )
        monkeypatch.setattr(home, 'check_home_reward_overlay', lambda _ctx: False)
        monkeypatch.setattr(home, 'check_news_checked', lambda _ctx, **_: True)
        monkeypatch.setattr(home, 'check_home_reward_confirm', lambda _ctx, **_: False)
        monkeypatch.setattr(sidebar, 'check_sidebar_page', lambda _ctx, **_options: False)
        sortie_tab = registry.get_tabs(PageName.SORTIE_MAP)['sortie']
        monkeypatch.setitem(
            registry._TABS[PageName.SORTIE_MAP],
            'sortie',
            NavTab(sortie_tab.click, lambda _ctx, **_options: True, '出征'),
        )
        monkeypatch.setattr(login, 'read_switch_entry_center', lambda _ctx: None)
        monkeypatch.setattr(login, 'read_enter_button_center', lambda _ctx: None)

    return _install
