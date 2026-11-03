"""模块功能：验证建造页标签激活状态的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.build.checker 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller.sidebar.build import (
    check_build_page,
    check_dismantle_tab,
)
from autowsgr.application.controller.sidebar.build import checker as build_checker


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

    monkeypatch.setattr(build_checker, 'expect_template', expect_template)
    return calls


def test_build_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """建造页默认落在「建造」标签，模板命中即算到达。"""
    calls = _install_recognition(monkeypatch, build_checker.BUILD_TAB_ROI)

    assert check_build_page(object()) is True
    assert calls[0]['roi'] is build_checker.BUILD_TAB_ROI
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0


def test_build_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """未落在建造标签时不算到达。"""
    _install_recognition(monkeypatch, build_checker.DISMANTLE_TAB_ROI)

    assert check_build_page(object()) is False


def test_dismantle_tab_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """解体标签激活时确认切换成功。"""
    _install_recognition(monkeypatch, build_checker.DISMANTLE_TAB_ROI)

    assert check_dismantle_tab(object()) is True


def test_dismantle_tab_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """建造标签激活时解体标签不成立。"""
    _install_recognition(monkeypatch, build_checker.BUILD_TAB_ROI)

    assert check_dismantle_tab(object()) is False
