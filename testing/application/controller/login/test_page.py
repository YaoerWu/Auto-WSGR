"""模块功能：验证登录页与区服选择页的单次点击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.login.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.login import page as login_page
from autowsgr.application.controller.login.page import LoginPage


def _stub_constants(monkeypatch: pytest.MonkeyPatch, *, server_count: int = 4) -> None:
    """用可断言的落点替身接管登录常量。"""
    monkeypatch.setattr(
        login_page,
        'constants',
        SimpleNamespace(
            CLICK_ENTER_GAME=(0.11, 0.12),
            CLICK_SWITCH_ENTRY=(0.21, 0.22),
            SERVER_POSITIONS=tuple((0.3 + index * 0.01, 0.4) for index in range(server_count)),
        ),
    )


def test_login_entry_clicks_fall_back_to_static_positions(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """没有识别中心时进入游戏与换区入口都点固定落点。"""
    _stub_constants(monkeypatch)

    page = LoginPage(ctx)
    page.click_enter_game()
    page.click_switch_entry()

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22)]


def test_login_entry_clicks_prefer_recognized_center(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """传入识别中心时优先用中心。"""
    _stub_constants(monkeypatch)

    page = LoginPage(ctx)
    page.click_enter_game((0.5, 0.6))
    page.click_switch_entry((0.7, 0.8))

    assert control.clicks == [(0.5, 0.6), (0.7, 0.8)]


@pytest.mark.parametrize('position', [0, 1, 3])
def test_click_server_uses_indexed_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
    position: int,
) -> None:
    """区服条目按序号点击对应落点。"""
    _stub_constants(monkeypatch)

    LoginPage(ctx).click_server(position)

    assert control.clicks == [(0.3 + position * 0.01, 0.4)]


@pytest.mark.parametrize('position', [-1, 4])
def test_click_server_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
    position: int,
) -> None:
    """序号越界时报错且不点任何位置。"""
    _stub_constants(monkeypatch)

    with pytest.raises(ValueError, match='区服条目序号超出范围'):
        LoginPage(ctx).click_server(position)

    assert control.clicks == []
