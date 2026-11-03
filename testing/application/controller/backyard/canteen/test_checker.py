"""模块功能：验证餐厅二级页检查器的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.backyard.canteen.checker 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller.backyard.canteen import checker as canteen_checker
from autowsgr.application.controller.backyard.canteen import constants


if TYPE_CHECKING:
    import pytest


def _install(
    monkeypatch: pytest.MonkeyPatch, visible_roi: object | None
) -> list[dict[str, object]]:
    """只让指定识别区域命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        matched = options.get('roi') is visible_roi
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(canteen_checker, 'expect_template', expect_template)
    return calls


def test_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """本页模板命中时确认到达。"""
    calls = _install(monkeypatch, constants.PAGE_ROI)

    assert canteen_checker.check_canteen_page(object()) is True
    assert calls[0]['roi'] is constants.PAGE_ROI
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0


def test_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """本页模板未命中时不算到达。"""
    _install(monkeypatch, None)

    assert canteen_checker.check_canteen_page(object()) is False


def test_page_absent_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """后识别：模板不在时期待离开成立。"""
    _install(monkeypatch, None)

    assert canteen_checker.check_canteen_page(object(), absent=True) is True
