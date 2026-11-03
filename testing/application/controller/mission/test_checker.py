"""模块功能：验证任务页检查器的识别判定契约。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.mission.checker 与 vision 识别入口。
边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import mission
from autowsgr.application.controller.mission import checker as mission_checker


if TYPE_CHECKING:
    import pytest


def _install(monkeypatch: pytest.MonkeyPatch, *, visible: frozenset[object] = frozenset()) -> list:
    """让指定区域命中，并记录每次识别的区域与 absent 参数。"""
    seen: list[tuple[object, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        roi = options.get('roi')
        seen.append((roi, options.get('absent')))
        matched = roi in visible
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(mission_checker, 'expect_template', expect_template)
    return seen


def test_mission_page_judges_tab_then_reward_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """页签命中才算在任务页，领奖浮窗盖住时前识别不判到达，后识别只判页签。"""
    seen = _install(monkeypatch, visible=frozenset({mission_checker.ALL_TAB_ROI}))

    assert mission.check_mission_page(object()) is True
    assert [entry[0] for entry in seen] == [
        mission_checker.ALL_TAB_ROI,
        mission_checker.REWARD_CONFIRM_BUTTON_ROI,
    ]

    seen = _install(monkeypatch, visible=frozenset())

    assert mission.check_mission_page(object()) is False
    assert [entry[0] for entry in seen] == [mission_checker.ALL_TAB_ROI]

    seen = _install(
        monkeypatch,
        visible=frozenset({mission_checker.ALL_TAB_ROI, mission_checker.REWARD_CONFIRM_BUTTON_ROI}),
    )

    assert mission.check_mission_page(object()) is False
    assert seen[-1] == (mission_checker.REWARD_CONFIRM_BUTTON_ROI, None)

    seen = _install(monkeypatch, visible=frozenset())

    assert mission.check_mission_page(object(), absent=True) is True
    assert seen == [(mission_checker.ALL_TAB_ROI, True)]


def test_mission_reward_buttons_follow_their_own_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """领奖按钮与兜底确认各自只看自己的区域，区域未命中时返回假。"""
    _install(monkeypatch, visible=frozenset({mission_checker.CLAIM_ALL_BUTTON_ROI}))
    assert mission.check_claim_all_button(object()) is True
    assert mission.check_mission_reward_confirm(object()) is False

    _install(monkeypatch, visible=frozenset({mission_checker.ALL_TAB_ROI}))
    assert mission.check_claim_all_button(object()) is False

    _install(monkeypatch, visible=frozenset({mission_checker.REWARD_CONFIRM_BUTTON_ROI}))
    assert mission.check_mission_reward_confirm(object()) is True
