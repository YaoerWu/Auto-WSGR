"""模块功能：验证主页单击控制器的落点契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.home.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.home import page as home_page
from autowsgr.application.controller.home.page import HomePage, Target
from autowsgr.application.navigation.types import PageName


def test_target_page_names_cover_the_navigation_map() -> None:
    """每个主页入口都映射到导航图里的页面名称。"""
    assert {target: target.page_name for target in Target} == {
        Target.SORTIE: PageName.SORTIE_MAP,
        Target.TASK: PageName.MISSION,
        Target.SIDEBAR: PageName.SIDEBAR,
        Target.BACKYARD: PageName.BACKYARD,
        Target.EVENT: PageName.EVENT_MAP,
    }


def test_go_to_clicks_configured_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """进入每个目标时点击该目标在常量表里的落点。"""
    nav = {
        target.name.lower(): (0.1 * index, 0.2 * index)
        for index, target in enumerate(Target, start=1)
    }
    monkeypatch.setattr(home_page, 'constants', SimpleNamespace(NAV_POSITIONS=nav))

    page = HomePage(ctx)
    for target in Target:
        page.go_to(target)

    assert control.clicks == [nav[target.name.lower()] for target in Target]


def test_go_to_rejects_target_without_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """目标没有配置落点时直接报错，不点任何位置。"""
    monkeypatch.setattr(home_page, 'constants', SimpleNamespace(NAV_POSITIONS={}))

    with pytest.raises(ValueError, match='主页没有该目标的落点'):
        HomePage(ctx).go_to(Target.SORTIE)

    assert control.clicks == []


def test_overlay_clicks_fall_back_to_static_positions(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """没有识别中心时四个浮窗按钮都点固定落点。"""
    overlay = {
        'news_checkbox': (0.01, 0.02),
        'news_close': (0.03, 0.04),
        'reward_claim': (0.05, 0.06),
        'reward_confirm': (0.07, 0.08),
    }
    monkeypatch.setattr(
        home_page,
        'constants',
        SimpleNamespace(NAV_POSITIONS={}, OVERLAY_POSITIONS=overlay),
    )

    page = HomePage(ctx)
    page.click_news_checkbox()
    page.click_news_close()
    page.click_reward_claim()
    page.click_reward_confirm()

    assert control.clicks == list(overlay.values())


def test_overlay_clicks_prefer_recognized_center(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """传入识别中心时优先用中心，空中心才回退固定落点。"""
    overlay = {
        'news_checkbox': (0.01, 0.02),
        'news_close': (0.03, 0.04),
        'reward_claim': (0.05, 0.06),
        'reward_confirm': (0.07, 0.08),
    }
    monkeypatch.setattr(
        home_page,
        'constants',
        SimpleNamespace(NAV_POSITIONS={}, OVERLAY_POSITIONS=overlay),
    )

    page = HomePage(ctx)
    page.click_news_checkbox((0.11, 0.12))
    page.click_reward_claim((0.13, 0.14))
    page.click_reward_confirm((0.15, 0.16))

    assert control.clicks == [(0.11, 0.12), (0.13, 0.14), (0.15, 0.16)]
