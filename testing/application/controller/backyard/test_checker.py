"""模块功能：验证后院主页检查器与入口中心的识别契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.backyard.checker 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import backyard
from autowsgr.application.controller.backyard import checker as backyard_checker


if TYPE_CHECKING:
    import pytest


def _install(
    monkeypatch: pytest.MonkeyPatch, hit_rois: tuple[object, ...]
) -> list[dict[str, object]]:
    """让列出的识别区域命中，其余不命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        roi = options.get('roi')
        regions = roi if isinstance(roi, tuple) else (roi,)
        matched = any(region in hit_rois for region in regions)
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(backyard_checker, 'expect_template', expect_template)
    return calls


def test_backyard_reached_by_entry_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口模板命中即算到达后院主页（身份就是其中一个入口）。"""
    calls = _install(monkeypatch, (backyard_checker.BATH_ENTRY_ROI,))

    assert backyard.check_backyard_page(object()) is True
    assert calls[0]['roi'] is backyard_checker.BACKYARD_ROI
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0


def test_backyard_absent_when_entry_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口模板不在时不算在后院主页。"""
    _install(monkeypatch, ())

    assert backyard.check_backyard_page(object()) is False


def test_backyard_absent_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """后识别：入口模板不在，期待离开成立（进二级页后整页被换掉）。"""
    _install(monkeypatch, ())

    assert backyard.check_backyard_page(object(), absent=True) is True


def test_entry_center_reads_matching_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口模板命中时给出它的归一化中心。"""
    calls: list[dict[str, object]] = []

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float]:
        calls.append(options)
        return (0.5, 0.5)

    monkeypatch.setattr(backyard_checker, 'expect_template_center', expect_template_center)

    assert backyard.read_canteen_entry_center(object()) == (0.5, 0.5)
    assert calls[0]['roi'] is backyard_checker.CANTEEN_ENTRY_ROI
    assert calls[0]['attempts'] == 1


def test_entry_center_returns_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口模板未命中时返回 None，由控制器用静态坐标兜底。"""
    monkeypatch.setattr(
        backyard_checker,
        'expect_template_center',
        lambda _ctx, **_options: None,
    )

    assert backyard.read_bath_entry_center(object()) is None
