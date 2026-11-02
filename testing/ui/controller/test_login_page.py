"""模块功能：验证登录控制器的单击落点。

直接调用方：项目测试运行器。

直接依赖：pytest、login 的控制器与落点表。

边界：用设备服务替身接管点击，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.login import LoginPage
from autowsgr.application.ui.controller.login import constants


class _Ctrl:
    """设备服务替身，记录点击落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))


def _build() -> tuple[LoginPage, _Ctrl]:
    """构造控制器与记录点击的替身。"""
    ctrl = _Ctrl()
    ctx: Any = SimpleNamespace(runtime=SimpleNamespace(ctrl=ctrl))
    return LoginPage(ctx), ctrl


def test_click_enter_game_clicks_enter_position() -> None:
    """进入游戏点击固定落点。"""
    page, ctrl = _build()

    page.click_enter_game()

    assert ctrl.clicks == [constants.CLICK_ENTER_GAME]


def test_switch_entry_clicks_switch_position() -> None:
    """打开区服列表点击换区入口落点。"""
    page, ctrl = _build()

    page.click_switch_entry()

    assert ctrl.clicks == [constants.CLICK_SWITCH_ENTRY]


def test_click_enter_game_uses_recognized_center() -> None:
    """传识别中心时点击中心，而不是固定落点。"""
    page, ctrl = _build()

    page.click_enter_game((0.25, 0.75))

    assert ctrl.clicks == [(0.25, 0.75)]


def test_switch_entry_uses_recognized_center() -> None:
    """传识别中心时点击中心，而不是固定落点。"""
    page, ctrl = _build()

    page.click_switch_entry((0.3, 0.4))

    assert ctrl.clicks == [(0.3, 0.4)]


@pytest.mark.parametrize('position', range(len(constants.SERVER_POSITIONS)))
def test_click_server_uses_position_table(position: int) -> None:
    """每个区服条目点击对应落点。"""
    page, ctrl = _build()

    page.click_server(position)

    assert ctrl.clicks == [constants.SERVER_POSITIONS[position]]


@pytest.mark.parametrize('position', [-1, len(constants.SERVER_POSITIONS)])
def test_click_server_rejects_out_of_range(position: int) -> None:
    """序号越界时拒绝点击。"""
    page, ctrl = _build()

    with pytest.raises(ValueError, match='区服条目序号超出范围'):
        page.click_server(position)

    assert ctrl.clicks == []
