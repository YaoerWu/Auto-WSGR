"""模块功能：验证后院主页跳转与返回的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.backyard.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.backyard import page as backyard_page
from autowsgr.application.controller.backyard.page import BackyardPage, BackyardTarget
from autowsgr.application.navigation.types import PageName


def _stub_constants(monkeypatch: pytest.MonkeyPatch, nav: dict[str, tuple[float, float]]) -> None:
    """用可断言的落点替身接管后院常量。"""
    monkeypatch.setattr(
        backyard_page,
        'constants',
        SimpleNamespace(
            NAV_POSITIONS=nav,
            CLICK_BACK=(0.9, 0.1),
            CLICK_HOME=(0.8, 0.2),
            CLICK_RANK_SKILL_LIST=(0.7, 0.3),
        ),
    )


def test_target_page_names_cover_the_navigation_map() -> None:
    """四个后院入口各自映射到导航图里的页面名称。"""
    assert {target: target.page_name for target in BackyardTarget} == {
        BackyardTarget.CANTEEN: PageName.CANTEEN,
        BackyardTarget.ACADEMY: PageName.ACADEMY,
        BackyardTarget.RANK_ROOM: PageName.RANK_ROOM,
        BackyardTarget.BATH: PageName.BATH,
    }


def test_go_to_clicks_configured_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """没有识别中心时点击常量表里的兜底落点。"""
    nav = {
        target.name.lower(): (0.1 * index, 0.2 * index)
        for index, target in enumerate(BackyardTarget, start=1)
    }
    _stub_constants(monkeypatch, nav)

    page = BackyardPage(ctx)
    for target in BackyardTarget:
        page.go_to(target)

    assert control.clicks == [nav[target.name.lower()] for target in BackyardTarget]


def test_go_to_prefers_recognized_center(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """识别中心存在时优先用它，不再读常量表落点。"""
    _stub_constants(monkeypatch, {'canteen': (0.1, 0.2)})

    BackyardPage(ctx).go_to(BackyardTarget.CANTEEN, (0.5, 0.6))

    assert control.clicks == [(0.5, 0.6)]


def test_go_to_rejects_target_without_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """既没有识别中心也没有兜底落点时直接报错。"""
    _stub_constants(monkeypatch, {})

    with pytest.raises(ValueError, match='后院没有该入口的落点'):
        BackyardPage(ctx).go_to(BackyardTarget.BATH)
    with pytest.raises(ValueError, match='后院没有该入口的落点'):
        BackyardPage(ctx).go_to(BackyardTarget.CANTEEN, (0.5, 0.6))

    assert control.clicks == []


def test_back_and_home_click_their_positions(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """退回上一级与回首页各点各的落点。"""
    _stub_constants(monkeypatch, {})

    page = BackyardPage(ctx)
    page.go_back()
    page.go_home()

    assert control.clicks == [(0.9, 0.1), (0.8, 0.2)]
