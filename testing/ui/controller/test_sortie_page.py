"""模块功能：验证出征页控制器的单击落点。

直接调用方：项目测试运行器。

直接依赖：pytest、main_page 的控制器与坐标表。

边界：用设备服务替身接管点击，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.sortie import (
    SortiePage,
    SortieTab,
)
from autowsgr.application.ui.controller.operations.sortie_page.main_page import (
    constants,
    recognition,
)


class _Ctrl:
    """设备服务替身，记录点击落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))


def _build() -> tuple[SortiePage, _Ctrl]:
    """构造控制器与记录点击的替身。"""
    ctrl = _Ctrl()
    ctx: Any = SimpleNamespace(runtime=SimpleNamespace(ctrl=ctrl))
    return SortiePage(ctx), ctrl


@pytest.mark.parametrize('tab', list(SortieTab))
def test_go_to_clicks_tab_position(tab: SortieTab) -> None:
    """每个标签在没有识别结果时点击固定落点。"""
    page, ctrl = _build()

    page.go_to(tab)

    assert ctrl.clicks == [constants.TAB_POSITIONS[tab.name.lower()]]


def test_go_to_prefers_recognized_center() -> None:
    """传入识别中心时优先使用中心。"""
    page, ctrl = _build()

    page.go_to(SortieTab.EXERCISE, (0.31, 0.05))

    assert ctrl.clicks == [(0.31, 0.05)]


def test_go_back_clicks_fixed_position() -> None:
    """返回使用固定落点。"""
    page, ctrl = _build()

    page.go_back()

    assert ctrl.clicks == [constants.CLICK_BACK]


def test_expedition_notification_uses_pixel_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """远征通知走 expect_pixels，使用约定签名并单帧探测。"""
    captured: dict[str, object] = {}

    def fake_expect_pixels(_ctx: object, **options: object) -> object:
        captured.update(options)
        return SimpleNamespace(satisfied=True)

    monkeypatch.setattr(recognition, 'expect_pixels', fake_expect_pixels)

    assert recognition.check_expedition_notification(object()) is True
    assert captured['signature'] is constants.EXPEDITION_NOTIF_SIGNATURE
    assert captured['attempts'] == 1
