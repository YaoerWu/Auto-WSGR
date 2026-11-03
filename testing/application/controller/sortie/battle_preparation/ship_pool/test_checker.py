"""模块功能：验证船池页面分类、页面判定与列表文字读取的契约。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.sortie.battle_preparation.ship_pool.checker 与 vision 识别入口。
边界：用替身接管模板加载与识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy
import pytest

from autowsgr.application.controller.sortie.battle_preparation.ship_pool import (
    checker as ship_pool_checker,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool import (
    constants as ship_pool_constants,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool.checker import (
    ShipPoolKind,
    check_search_input,
    check_ship_pool_page,
    read_ship_list_texts,
    read_ship_pool_kind,
)
from autowsgr.common.vision import RecognitionProfile, TextDetection


if TYPE_CHECKING:
    from typing import Any


@pytest.fixture(autouse=True)
def _stub_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    """把模板加载换成可比较哨兵，并让所有识别入口默认返回空结论。"""

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    def _template(_ctx: Any, **_options: Any) -> SimpleNamespace:
        return SimpleNamespace(
            satisfied=False,
            observation=[SimpleNamespace(matched=False) for _ in range(4)],
        )

    def _pixels(_ctx: Any, **_options: Any) -> SimpleNamespace:
        return SimpleNamespace(satisfied=False)

    def _ocr(_ctx: Any, **_options: Any) -> SimpleNamespace:
        return SimpleNamespace(screenshot=None, observation=[])

    monkeypatch.setattr(ship_pool_checker, 'load_ui_template', load_template)
    monkeypatch.setattr(ship_pool_checker, 'expect_template', _template)
    monkeypatch.setattr(ship_pool_checker, 'expect_pixels', _pixels)
    monkeypatch.setattr(ship_pool_checker, 'expect_ocr', _ocr)


def _install_template(
    monkeypatch: pytest.MonkeyPatch,
    *,
    satisfied: bool = True,
    matched: tuple[bool, bool, bool, bool] = (False, False, False, False),
) -> list[dict[str, Any]]:
    """让模板识别返回指定命中组合，并记录调用参数。"""
    calls: list[dict[str, Any]] = []

    def expect_template(_ctx: Any, **options: Any) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(
            satisfied=satisfied,
            observation=[SimpleNamespace(matched=flag) for flag in matched],
        )

    monkeypatch.setattr(ship_pool_checker, 'expect_template', expect_template)
    return calls


def _install_pixels(monkeypatch: pytest.MonkeyPatch, satisfied: bool) -> list[dict[str, Any]]:
    """让像素识别返回指定结论，并记录调用参数。"""
    calls: list[dict[str, Any]] = []

    def expect_pixels(_ctx: Any, **options: Any) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=satisfied)

    monkeypatch.setattr(ship_pool_checker, 'expect_pixels', expect_pixels)
    return calls


def _install_ocr(monkeypatch: pytest.MonkeyPatch, result: SimpleNamespace) -> list[dict[str, Any]]:
    """让 OCR 返回给定结果，并记录调用参数。"""
    calls: list[dict[str, Any]] = []

    def expect_ocr(_ctx: Any, **options: Any) -> SimpleNamespace:
        calls.append(options)
        return result

    monkeypatch.setattr(ship_pool_checker, 'expect_ocr', expect_ocr)
    return calls


def _feature_templates() -> tuple[tuple[str, str], ...]:
    """按 checker 登记顺序取四个特征模板的哨兵值。"""
    return tuple(
        (ship_pool_checker.constants.TEMPLATE_NAMESPACE, filename)
        for filename, _roi in ship_pool_constants.KIND_FEATURES
    )


def test_ship_pool_page_matches_four_features_in_one_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面判定一次匹配四个特征模板，期望方向与重试节奏原样透传。"""
    calls = _install_template(monkeypatch, satisfied=True)

    assert check_ship_pool_page(object()) is True
    assert calls[0]['template'] == _feature_templates()
    assert calls[0]['roi'] == tuple(roi for _filename, roi in ship_pool_constants.KIND_FEATURES)
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0
    assert calls[0]['absent'] is False

    calls.clear()
    assert check_ship_pool_page(object(), attempts=2, interval_seconds=0.25, absent=True) is True
    assert calls[0]['attempts'] == 2
    assert calls[0]['interval_seconds'] == 0.25
    assert calls[0]['absent'] is True

    _install_template(monkeypatch, satisfied=False)
    assert check_ship_pool_page(object()) is False


@pytest.mark.parametrize(
    ('matched', 'expected'),
    [
        ((True, False, False, False), ShipPoolKind.STRENGTHEN),
        ((False, True, False, False), ShipPoolKind.DISMANTLE),
        ((False, False, True, True), ShipPoolKind.SORTIE),
        ((False, False, True, False), ShipPoolKind.DECISIVE),
        ((False, False, False, True), ShipPoolKind.ACADEMY),
        ((False, False, False, False), None),
    ],
)
def test_read_ship_pool_kind_maps_feature_combinations(
    monkeypatch: pytest.MonkeyPatch,
    matched: tuple[bool, bool, bool, bool],
    expected: ShipPoolKind | None,
) -> None:
    """四个特征的命中组合唯一决定船池类别；全不中说明当前不是船池。"""
    calls = _install_template(monkeypatch, matched=matched)

    assert read_ship_pool_kind(object()) is expected
    # 读取语义只截一帧，不按重试窗口反复等。
    assert calls[0]['attempts'] == 1
    assert calls[0]['absent'] is False


def test_check_search_input_uses_keyboard_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """搜索输入态认软键盘签名，结论与重试节奏原样透传。"""
    calls = _install_pixels(monkeypatch, True)

    assert check_search_input(object(), attempts=3, interval_seconds=0.5) is True
    assert calls[0] == {
        'signature': ship_pool_checker.constants.SEARCH_INPUT_SIGNATURE,
        'attempts': 3,
        'interval_seconds': 0.5,
    }

    _install_pixels(monkeypatch, False)
    assert check_search_input(object()) is False


def test_read_ship_list_texts_filters_frame_regions_by_list_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """整帧识别后只保留中心落在列表区域的文字，并换算成归一化位置。"""
    frame = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    result = SimpleNamespace(
        screenshot=frame,
        observation=[
            TextDetection(' 企业 ', 0.9, (10, 120, 30, 140)),
            TextDetection('   ', 0.8, (1, 2, 3, 4)),
            TextDetection('无位置', 0.7, None),
            TextDetection('俾斯麦', 0.6, (100, 200, 300, 400)),
            TextDetection('列表外', 0.5, (1100, 300, 1200, 340)),
        ],
    )
    calls = _install_ocr(monkeypatch, result)

    texts = read_ship_list_texts(object())

    assert [item.text for item in texts] == ['企业', '俾斯麦']
    assert texts[0].center == (20 / 1280, 130 / 720)
    assert texts[0].region == (10 / 1280, 120 / 720, 30 / 1280, 140 / 720)
    assert texts[1].center == (200 / 1280, 300 / 720)
    assert calls[0] == {
        'recognition_profile': RecognitionProfile.FULL,
        'attempts': 1,
    }


def test_read_ship_list_texts_returns_empty_without_frame_or_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有截图就无法换算位置，没有识别结果时也没有条目，两种情况都返回空元组。"""
    _install_ocr(
        monkeypatch,
        SimpleNamespace(screenshot=None, observation=[TextDetection('企业', 0.9, (0, 0, 1, 1))]),
    )

    assert read_ship_list_texts(object()) == ()

    frame = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    _install_ocr(monkeypatch, SimpleNamespace(screenshot=frame, observation=[]))

    assert read_ship_list_texts(object()) == ()
