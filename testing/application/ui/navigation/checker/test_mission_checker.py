"""模块功能：验证任务页检查器的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.mission 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import mission
from autowsgr.application.controller.mission import checker as mission_checker


if TYPE_CHECKING:
    import pytest


def _install(monkeypatch: pytest.MonkeyPatch, visible_roi: object | None) -> None:
    """让指定识别区域命中，其余不命中。"""

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        roi = options.get('roi')
        matched = roi is visible_roi
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(mission_checker, 'expect_template', expect_template)


def test_mission_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """「全部」页签命中时确认在任务页。"""
    _install(monkeypatch, mission_checker.ALL_TAB_ROI)

    assert mission.check_mission_page(object()) is True


def test_mission_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """页签未命中时不算在任务页。"""
    _install(monkeypatch, mission_checker.CLAIM_ALL_BUTTON_ROI)

    assert mission.check_mission_page(object()) is False


def test_claim_all_button_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """有奖励可领时「全部领取」按钮出现。"""
    _install(monkeypatch, mission_checker.CLAIM_ALL_BUTTON_ROI)

    assert mission.check_claim_all_button(object()) is True


def test_claim_all_button_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """奖励都领完时按钮不存在。"""
    _install(monkeypatch, mission_checker.ALL_TAB_ROI)

    assert mission.check_claim_all_button(object()) is False


def test_reward_confirm_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """「获得」浮窗的「确认」按钮命中时确认浮窗弹出。"""
    _install(monkeypatch, mission_checker.REWARD_CONFIRM_BUTTON_ROI)

    assert mission.check_mission_reward_confirm(object()) is True


def test_reward_confirm_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗收起后确认入口返回假。"""
    _install(monkeypatch, mission_checker.ALL_TAB_ROI)

    assert mission.check_mission_reward_confirm(object()) is False
