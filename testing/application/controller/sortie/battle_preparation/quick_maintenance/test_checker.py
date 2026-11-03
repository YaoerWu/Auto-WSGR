"""模块功能：验证快速整备状态与修理存量的识别契约。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.sortie.battle_preparation.quick_maintenance.checker 与
vision 识别入口。
边界：用替身接管模板加载与三路识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance import (
    check_auto_supply_enabled,
    check_quick_repair_active,
    read_all_repair_center,
    read_auto_supply_center,
    read_quick_repair_center,
    read_repair_tool_count,
)
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance import (
    checker as quick_checker,
)
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance import (
    constants as quick_constants,
)
from autowsgr.common.vision import TextDetection


if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def _stub_template_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """把模板加载换成命名空间与文件名组成的可比较哨兵。"""

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    monkeypatch.setattr(quick_checker, 'load_ui_template', load_template)


def _install_template(
    monkeypatch: pytest.MonkeyPatch,
    satisfied: bool,
) -> list[dict[str, object]]:
    """让模板识别返回指定结论，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=satisfied)

    monkeypatch.setattr(quick_checker, 'expect_template', expect_template)
    return calls


def test_auto_supply_reads_checkbox_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """自动补给只认勾选框开启态模板，勾上与否决定结论。"""
    calls = _install_template(monkeypatch, True)

    assert check_auto_supply_enabled(object()) is True
    assert calls[0]['template'] == (
        quick_checker.constants.TEMPLATE_NAMESPACE,
        quick_constants.AUTO_SUPPLY_TEMPLATE,
    )
    assert calls[0]['roi'] is quick_constants.AUTO_SUPPLY_ROI

    _install_template(monkeypatch, False)

    assert check_auto_supply_enabled(object()) is False


def test_quick_repair_requires_tab_and_all_repair_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页签与「全部修理」按钮必须同帧同时命中，并带面板联动的重试节奏。"""
    calls = _install_template(monkeypatch, True)

    assert check_quick_repair_active(object()) is True
    assert calls[0]['template'] == (
        (quick_checker.constants.TEMPLATE_NAMESPACE, quick_constants.QUICK_REPAIR_TEMPLATE),
        (quick_checker.constants.TEMPLATE_NAMESPACE, quick_constants.ALL_REPAIR_BUTTON_TEMPLATE),
    )
    assert calls[0]['roi'] == (
        quick_constants.QUICK_REPAIR_ROI,
        quick_constants.ALL_REPAIR_BUTTON_ROI,
    )
    assert calls[0]['min_matches'] == 2
    assert calls[0]['attempts'] == 4
    assert calls[0]['interval_seconds'] == 0.5

    _install_template(monkeypatch, False)

    assert check_quick_repair_active(object()) is False


@pytest.mark.parametrize(
    ('texts', 'expected'),
    [
        (('7188',), 7188),
        (('7', '7188'), 7),
        ((), None),
        (('',), None),
        (('7 188',), None),
    ],
)
def test_read_repair_tool_count(
    monkeypatch: pytest.MonkeyPatch,
    texts: tuple[str, ...],
    expected: int | None,
) -> None:
    """只接受纯数字识别结果，空格或被拆开的文本视为不可读。"""
    calls: list[dict[str, object]] = []
    observation = [TextDetection(recognized_text=text, confidence_score=0.9) for text in texts]

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=bool(observation), observation=observation)

    monkeypatch.setattr(quick_checker, 'expect_ocr', expect_ocr)

    assert read_repair_tool_count(object()) == expected
    assert calls[0]['roi'] is quick_constants.REPAIR_STOCK_ROI
    assert calls[0]['allowlist'] == '0123456789'
    assert calls[0]['attempts'] == 1


_CENTER_CASES: tuple[tuple[Callable[[object], tuple[float, float] | None], str, object], ...] = (
    (
        read_auto_supply_center,
        quick_constants.AUTO_SUPPLY_TEMPLATE,
        quick_constants.AUTO_SUPPLY_ROI,
    ),
    (
        read_quick_repair_center,
        quick_constants.QUICK_REPAIR_TEMPLATE,
        quick_constants.QUICK_REPAIR_ROI,
    ),
    (
        read_all_repair_center,
        quick_constants.ALL_REPAIR_BUTTON_TEMPLATE,
        quick_constants.ALL_REPAIR_BUTTON_ROI,
    ),
)


def test_center_readers_use_their_own_template_and_allow_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三个落点读取各自用对应模板与区域，未命中时返回空交由调用方兜底。"""
    for reader, filename, roi in _CENTER_CASES:
        calls: list[dict[str, object]] = []

        def expect_template_center(
            _ctx: object,
            _calls: list[dict[str, object]] = calls,
            **options: object,
        ) -> tuple[float, float]:
            _calls.append(options)
            return (0.25, 0.75)

        monkeypatch.setattr(quick_checker, 'expect_template_center', expect_template_center)

        assert reader(object()) == (0.25, 0.75)
        assert calls[0]['template'] == (quick_checker.constants.TEMPLATE_NAMESPACE, filename)
        assert calls[0]['roi'] is roi

        monkeypatch.setattr(quick_checker, 'expect_template_center', lambda *_a, **_k: None)

        assert reader(object()) is None
