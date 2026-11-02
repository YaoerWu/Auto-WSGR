"""模块功能：验证出征准备页检查器的一次判层契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.sortie.battle_preparation 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie import battle_preparation
from autowsgr.application.controller.sortie.battle_preparation import (
    checker as battle_preparation_checker,
)


if TYPE_CHECKING:
    from autowsgr.application.navigation.types import PageName


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hit_index: int | None,
    calls: list[dict[str, object]],
) -> None:
    """用替身接管识别入口：只让指定下标的模板命中，并记下调用参数。"""

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        count = len(options['template'])  # type: ignore[arg-type]
        observation = [SimpleNamespace(matched=(index == hit_index)) for index in range(count)]
        return SimpleNamespace(satisfied=hit_index is not None, observation=observation)

    monkeypatch.setattr(battle_preparation_checker, 'expect_template', expect_template)


def test_reads_all_four_templates_in_one_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """四个模板共享同一个识别区域，只走一次截图。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, hit_index=0, calls=calls)

    battle_preparation.read_battle_preparation_layer(object())

    assert len(calls) == 1
    assert len(calls[0]['template']) == len(battle_preparation_checker._PAGE_TEMPLATES)  # type: ignore[arg-type]
    assert calls[0]['roi'] is battle_preparation_checker.BATTLE_PREPARATION_ROI


@pytest.mark.parametrize(
    ('hit_index', 'expected'),
    tuple(
        (index, page) for index, (page, _) in enumerate(battle_preparation_checker._PAGE_TEMPLATES)
    ),
)
def test_reports_the_page_whose_template_matched(
    monkeypatch: pytest.MonkeyPatch,
    hit_index: int,
    expected: PageName,
) -> None:
    """命中哪个模板就报哪个页面。"""
    _install_recognition(monkeypatch, hit_index=hit_index, calls=[])

    assert battle_preparation.read_battle_preparation_layer(object()) == (expected,)


def test_reports_nothing_when_no_template_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    """四个模板都不命中时返回空元组。"""
    _install_recognition(monkeypatch, hit_index=None, calls=[])

    assert battle_preparation.read_battle_preparation_layer(object()) == ()
