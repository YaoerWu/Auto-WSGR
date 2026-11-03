"""模块功能：验证改造页标签激活状态的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.intensify.checker 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller.sidebar.intensify import (
    check_intensify_page,
    check_remold_tab,
    check_skill_tab,
)
from autowsgr.application.controller.sidebar.intensify import (
    checker as intensify_checker,
)


if TYPE_CHECKING:
    import pytest


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    visible_roi: object | None,
) -> list[dict[str, object]]:
    """只让指定识别区域命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        matched = options.get('roi') is visible_roi
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(intensify_checker, 'expect_template', expect_template)
    return calls


def test_intensify_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """改造页默认落在「强化」标签，模板命中即算到达。"""
    calls = _install_recognition(monkeypatch, intensify_checker.constants.INTENSIFY_TAB_ROI)

    assert check_intensify_page(object()) is True
    assert calls[0]['roi'] is intensify_checker.constants.INTENSIFY_TAB_ROI
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0


def test_intensify_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """未落在强化标签时不算到达。"""
    _install_recognition(monkeypatch, intensify_checker.constants.SKILL_TAB_ROI)

    assert check_intensify_page(object()) is False


def test_remold_and_skill_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """改造与技能标签各自能被确认，互不误判。"""
    _install_recognition(monkeypatch, intensify_checker.constants.REMOLD_TAB_ROI)
    assert check_remold_tab(object()) is True
    assert check_skill_tab(object()) is False

    _install_recognition(monkeypatch, intensify_checker.constants.SKILL_TAB_ROI)
    assert check_skill_tab(object()) is True
    assert check_remold_tab(object()) is False
