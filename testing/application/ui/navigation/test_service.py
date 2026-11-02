"""模块功能：验证导航入口的算路执行、浮窗链、回退与登录链路。

直接调用方：项目测试运行器。

直接依赖：pytest、navigation 的入口与注册中心、dispatch 会话状态、controller 的页面落点常量。

边界：用替身接管设备点击与页面确认，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller import home
from autowsgr.application.controller.login import checker as login_checker
from autowsgr.application.ui.controller.home.main_page import constants as home_constants
from autowsgr.application.ui.controller.login import constants as login_constants
from autowsgr.application.ui.controller.operations.sortie_page.main_page import (
    constants as sortie_constants,
)
from autowsgr.application.ui.navigation import registry
from autowsgr.application.ui.navigation.service import NavigationService
from autowsgr.application.ui.navigation.types import NavigationError, NavTab, PageName
from autowsgr.dispatch.session import SessionState


def test_goto_page_clicks_and_confirms(ctx: Any, accept_path: Any) -> None:
    """导航按路径逐步点击并确认到达。"""
    accept_path(PageName.SORTIE_MAP)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME.value)

    service.navigate_to(PageName.SORTIE_MAP)

    # 首页点出征入口，进入后再点一次「出征」标签（远征可收时页面会先停在远征）。
    assert ctx.runtime.ctrl.clicks == [
        (0.9430, 0.9069),
        sortie_constants.TAB_POSITIONS['sortie'],
    ]
    assert session.current_page() == PageName.SORTIE_MAP.value


def test_navigate_from_news_overlay_walks_popup_chain(ctx: Any, accept_path: Any) -> None:
    """停在每日公告上时，回主页会依次走完浮窗链。"""
    accept_path(PageName.HOME)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME_NEWS.value)

    service.navigate_to(PageName.HOME)

    assert session.current_page() == PageName.HOME.value


def test_goto_page_rejects_failed_confirmation(
    ctx: Any, accept_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """到达确认失败时抛错。

    出征页这条边声明了标签，因此到达确认由标签的 checker 负责，
    页面级确认不参与；这里让标签的 checker 判失败。
    """
    accept_path(PageName.SORTIE_MAP)
    sortie_tab = registry.get_tabs(PageName.SORTIE_MAP)['sortie']
    monkeypatch.setitem(
        registry._TABS[PageName.SORTIE_MAP],
        'sortie',
        NavTab(sortie_tab.click, lambda _ctx, **_options: False, '出征'),
    )
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME.value)

    with pytest.raises(NavigationError, match='标签切换失败'):
        service.navigate_to(PageName.SORTIE_MAP)


def test_news_edge_closes_and_ticks_checkbox(
    ctx: Any, accept_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """公告边：未勾选时先勾上再关闭。"""
    accept_path(PageName.HOME_REWARD)
    monkeypatch.setattr(
        home,
        'read_news_overlay',
        lambda _ctx: SimpleNamespace(matched=True, checked=False),
    )
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME_NEWS.value)

    service.navigate_to(PageName.HOME_REWARD)

    clicks = ctx.runtime.ctrl.clicks
    assert home_constants.OVERLAY_POSITIONS['news_checkbox'] in clicks
    assert home_constants.OVERLAY_POSITIONS['news_close'] in clicks


def test_news_edge_does_nothing_without_overlay(ctx: Any, accept_path: Any) -> None:
    """公告边：没有公告就什么都不做，不空点。"""
    accept_path(PageName.HOME_REWARD)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME_NEWS.value)

    service.navigate_to(PageName.HOME_REWARD)

    assert ctx.runtime.ctrl.clicks == []


def test_reward_edge_claims_then_confirms(
    ctx: Any, accept_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """奖励边与确认边：有浮窗时各自点各自的位置。"""
    accept_path(PageName.HOME)
    monkeypatch.setattr(home, 'check_home_reward_overlay', lambda _ctx: True)
    monkeypatch.setattr(home, 'check_home_reward_confirm', lambda _ctx, **_: True)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME_REWARD.value)

    service.navigate_to(PageName.HOME)

    clicks = ctx.runtime.ctrl.clicks
    assert home_constants.OVERLAY_POSITIONS['reward_claim'] in clicks
    assert home_constants.OVERLAY_POSITIONS['reward_confirm'] in clicks


def test_go_back_returns_to_previous_page(ctx: Any, accept_path: Any) -> None:
    """回退到导航栈里的上一个页面。"""
    accept_path(PageName.HOME_NEWS)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.HOME_NEWS.value)
    session.push_page(PageName.SORTIE_MAP.value)

    service.navigate_back()

    assert session.current_page() == PageName.HOME_NEWS.value


def test_go_back_rejects_empty_stack(ctx: Any) -> None:
    """导航栈为空时回退抛错。"""
    service = NavigationService(ctx, session=SessionState())

    with pytest.raises(NavigationError, match='导航栈为空'):
        service.navigate_back()


def test_login_link_clicks_switch_entry_and_server(
    ctx: Any, accept_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """登录页 → 区服选择页 → 登录页 按各自落点点击。"""
    accept_path(PageName.SERVER_SELECT)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.LOGIN_PAGE.value)

    service.navigate_to(PageName.SERVER_SELECT)
    assert ctx.runtime.ctrl.clicks == [login_constants.CLICK_SWITCH_ENTRY]

    # 第二跳的目标换成了登录页，替身要跟着换；
    # OCR 定位失败时按静态映射兜底，仍要点到目标区服条目。
    accept_path(PageName.LOGIN_PAGE)
    monkeypatch.setattr(login_checker, 'read_server_position', lambda _ctx, _name: None)
    service.navigate_to(PageName.LOGIN_PAGE, server='昆西')
    assert ctx.runtime.ctrl.clicks[-1] == login_constants.SERVER_POSITIONS[2]


def test_login_to_home_clicks_enter_game(ctx: Any, accept_path: Any) -> None:
    """登录页 → 主页 点击进入游戏落点，落点是浮窗链的第一站。"""
    accept_path(PageName.HOME)
    session = SessionState()
    service = NavigationService(ctx, session=session)
    session.push_page(PageName.LOGIN_PAGE.value)

    service.navigate_to(PageName.HOME)

    assert ctx.runtime.ctrl.clicks == [login_constants.CLICK_ENTER_GAME]


# ── 冷启动清浮窗 ────────────────────────────────────────────────────────────


def test_cold_start_dismisses_overlay_and_keeps_underlying_page(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """冷启动停在演习浮窗上：先清掉浮窗，栈只落到底下那层演习页。"""
    from autowsgr.application.controller.sortie import exercise
    from autowsgr.application.ui.navigation import executor as executor_module

    monkeypatch.setattr(executor_module.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(registry, 'probe_domains', lambda _ctx, **_options: (PageName.EXERCISE,))
    monkeypatch.setattr(exercise, 'read_overlay_close_center', lambda _ctx: None)

    session = SessionState()
    service = NavigationService(ctx, session=session)
    layers = iter(
        [
            (PageName.EXERCISE_RIVAL_CONFIRM, PageName.EXERCISE),
            (PageName.EXERCISE,),
        ]
    )
    monkeypatch.setattr(service._executor, 'detect_layer', lambda **_options: next(layers))

    assert service._current_page() is PageName.EXERCISE
    assert session.pop_page() == PageName.EXERCISE.value
    assert session.pop_page() is None


def test_cold_start_dismisses_news_overlay_to_home(
    ctx: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """冷启动停在公告上：公告把主页整个挡住，清完浮窗链后落到主页。"""
    from autowsgr.application.ui.navigation import executor as executor_module

    monkeypatch.setattr(executor_module.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(registry, 'probe_domains', lambda _ctx, **_options: (PageName.HOME,))
    monkeypatch.setattr(
        home, 'read_news_overlay', lambda _ctx, **_options: SimpleNamespace(matched=False)
    )
    monkeypatch.setattr(home, 'check_home_reward_overlay', lambda _ctx, **_options: False)
    monkeypatch.setattr(home, 'check_home_reward_confirm', lambda _ctx, **_options: False)
    monkeypatch.setattr(registry.sidebar, 'check_sidebar_page', lambda _ctx, **_options: False)

    session = SessionState()
    service = NavigationService(ctx, session=session)
    layers = iter([(PageName.HOME_NEWS,), (PageName.HOME,)])
    monkeypatch.setattr(service._executor, 'detect_layer', lambda **_options: next(layers))

    assert service._current_page() is PageName.HOME
    assert session.pop_page() == PageName.HOME.value
    assert session.pop_page() is None


# ── 侧边栏域与页面内标签 ──────────────────────────────────────────────────────
