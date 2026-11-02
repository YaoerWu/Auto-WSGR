"""模块功能：验证主页控制器的单击落点。

直接调用方：项目测试运行器。

直接依赖：pytest、main_page 的控制器与坐标表。

边界：用设备服务替身接管点击，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.home import (
    HomePage,
    Target,
)
from autowsgr.application.ui.controller.home.main_page import (
    constants,
    recognition,
)


class _Ctrl:
    """设备服务替身，记录点击落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))


def _build() -> tuple[HomePage, _Ctrl]:
    """构造控制器与记录点击的替身。"""
    ctrl = _Ctrl()
    ctx: Any = SimpleNamespace(runtime=SimpleNamespace(ctrl=ctrl))
    return HomePage(ctx), ctrl


@pytest.mark.parametrize('target', list(Target))
def test_go_to_clicks_nav_position(target: Target) -> None:
    """每个导航目标点击对应落点。"""
    page, ctrl = _build()

    page.go_to(target)

    assert ctrl.clicks == [constants.NAV_POSITIONS[target.name.lower()]]


def test_go_to_rejects_missing_position(monkeypatch: pytest.MonkeyPatch) -> None:
    """目标没有配置落点时被拒绝。"""
    page, _ = _build()
    monkeypatch.delitem(constants.NAV_POSITIONS, 'event')

    with pytest.raises(ValueError, match='没有该目标的落点'):
        page.go_to(Target.EVENT)


@pytest.mark.parametrize(
    ('action', 'name'),
    [
        ('click_news_checkbox', 'news_checkbox'),
        ('click_news_close', 'news_close'),
        ('click_reward_claim', 'reward_claim'),
        ('click_reward_confirm', 'reward_confirm'),
    ],
)
def test_overlay_clicks_use_fixed_positions(action: str, name: str) -> None:
    """四个每日浮窗按钮都用控制器持有的固定落点。"""
    page, ctrl = _build()

    getattr(page, action)()

    assert ctrl.clicks == [constants.OVERLAY_POSITIONS[name]]


@pytest.mark.parametrize(
    'action',
    ['click_news_checkbox', 'click_reward_claim', 'click_reward_confirm'],
)
def test_overlay_click_uses_recognized_center(action: str) -> None:
    """传入识别中心时点击中心，而不是固定落点。"""
    page, ctrl = _build()

    getattr(page, action)((0.25, 0.75))

    assert ctrl.clicks == [(0.25, 0.75)]


def _install_pixels(monkeypatch: pytest.MonkeyPatch, *, matched: bool) -> dict[str, object]:
    """用替身接管像素识别，记录调用参数。"""
    captured: dict[str, object] = {}

    def fake_expect_pixels(_ctx: object, **options: object) -> object:
        captured.update(options)
        return SimpleNamespace(satisfied=matched)

    monkeypatch.setattr(recognition, 'expect_pixels', fake_expect_pixels)
    return captured


def test_expedition_notification_uses_pixel_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """远征通知走 expect_pixels，使用约定签名并单帧探测。"""
    captured = _install_pixels(monkeypatch, matched=True)

    assert recognition.check_expedition_ready(object()) is True
    assert captured['signature'] is constants.EXPEDITION_READY_SIGNATURE
    assert captured['attempts'] == 1


def test_task_notification_reports_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    """任务通知未命中时返回假，且使用任务签名。"""
    captured = _install_pixels(monkeypatch, matched=False)

    assert recognition.check_task_ready(object()) is False
    assert captured['signature'] is constants.TASK_READY_SIGNATURE
