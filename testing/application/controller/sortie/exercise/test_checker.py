"""模块功能：验证演习浮窗按钮中心与对手六槽位读数的契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.exercise.checker 与 vision 的中心读取、OCR 入口。

边界：用替身接管模板加载与识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie.exercise import checker as exercise_checker
from autowsgr.application.controller.sortie.exercise import constants as exercise_constants
from autowsgr.application.controller.sortie.exercise.checker import (
    read_overlay_challenge_center,
    read_overlay_close_center,
    read_overlay_refresh_center,
    read_rival_ships,
)
from autowsgr.application.controller.sortie.exercise.constants import (
    EXERCISE_RIVAL_SLOTS,
)
from autowsgr.application.controller.types import ShipType
from autowsgr.common.vision import RecognitionProfile, TextDetection


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


# ── 按钮中心 ────────────────────────────────────────────────────────────────


def _install_center(
    monkeypatch: pytest.MonkeyPatch,
    center: tuple[float, float] | None,
) -> list[dict[str, object]]:
    """让中心读取返回指定落点，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float] | None:
        calls.append(options)
        return center

    monkeypatch.setattr(exercise_checker, 'load_ui_template', load_template)
    monkeypatch.setattr(exercise_checker, 'expect_template_center', expect_template_center)
    return calls


_CASES: tuple[tuple[Callable[[object], tuple[float, float] | None], str, object], ...] = (
    (
        read_overlay_close_center,
        exercise_constants.OVERLAY_CLOSE_TEMPLATE,
        exercise_constants.OVERLAY_CLOSE_ROI,
    ),
    (
        read_overlay_refresh_center,
        exercise_constants.OVERLAY_REFRESH_TEMPLATE,
        exercise_constants.OVERLAY_REFRESH_ROI,
    ),
    (
        read_overlay_challenge_center,
        exercise_constants.OVERLAY_CHALLENGE_TEMPLATE,
        exercise_constants.OVERLAY_CHALLENGE_ROI,
    ),
)


@pytest.mark.parametrize(('reader', 'filename', 'roi'), _CASES)
def test_each_button_reads_its_template_center(
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[object], tuple[float, float] | None],
    filename: str,
    roi: object,
) -> None:
    """三个按钮各自读自己的模板与区域，并原样返回中心。"""
    calls = _install_center(monkeypatch, (0.25, 0.75))

    assert reader(object()) == (0.25, 0.75)
    assert calls[0]['template'] == (exercise_checker.constants.TEMPLATE_NAMESPACE, filename)
    assert calls[0]['roi'] is roi
    assert calls[0]['attempts'] == 1


@pytest.mark.parametrize(('reader', '_filename', '_roi'), _CASES)
def test_missing_button_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[object], tuple[float, float] | None],
    _filename: str,
    _roi: object,
) -> None:
    """模板未命中时中心为空，由调用方回落到固定坐标。"""
    _install_center(monkeypatch, None)

    assert reader(object()) is None


# ── 对手六槽位 ──────────────────────────────────────────────────────────────


def _detections(texts: Sequence[str]) -> list[TextDetection]:
    """把一组文本包装成 OCR 识别结果。"""
    return [TextDetection(recognized_text=text, confidence_score=0.9) for text in texts]


def _install_ocr(
    monkeypatch: pytest.MonkeyPatch,
    type_texts: Sequence[Sequence[str]],
    level_texts: Sequence[Sequence[str]],
) -> list[dict[str, object]]:
    """按识别区域分派舰种与等级两组替身结果，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        texts = (
            type_texts if options['roi'] is exercise_constants.RIVAL_SHIP_TYPE_ROIS else level_texts
        )
        return SimpleNamespace(
            satisfied=True,
            observation=[_detections(group) for group in texts],
        )

    monkeypatch.setattr(exercise_checker, 'expect_ocr', expect_ocr)
    return calls


def test_reads_six_rival_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    """六个槽位按顺序读出舰种与等级，未知舰种为空。"""
    type_texts = [
        ('航母',),
        ('轻母',),
        ('战列',),
        ('驱逐',),
        ('潜艇',),
        ('其他',),
    ]
    level_texts = [
        ('LV.110',),
        ('LV.100',),
        ('LV.95',),
        ('LV.90',),
        ('LV.1',),
        ('LV.80',),
    ]
    calls = _install_ocr(monkeypatch, type_texts, level_texts)

    rivals = read_rival_ships(object())

    assert len(rivals) == EXERCISE_RIVAL_SLOTS
    assert [rival.slot for rival in rivals] == [1, 2, 3, 4, 5, 6]
    assert [rival.ship_type for rival in rivals] == [
        ShipType.CV,
        ShipType.CVL,
        ShipType.BB,
        ShipType.DD,
        ShipType.SS,
        None,
    ]
    assert [rival.level for rival in rivals] == [110, 100, 95, 90, 1, 80]
    assert calls[0]['roi'] is exercise_constants.RIVAL_SHIP_TYPE_ROIS
    assert calls[0]['attempts'] == 1
    assert calls[0]['recognition_profile'] is RecognitionProfile.SINGLE_LINE
    assert calls[1]['roi'] is exercise_constants.RIVAL_SHIP_LEVEL_ROIS
    assert calls[1]['allowlist'] == exercise_checker.constants.LEVEL_ALLOWLIST


def test_ship_type_accepts_split_detections(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一区域被切成两段识别结果时拼接后再匹配。"""
    type_texts = [('轻', '母')] + [('航母',)] * 5
    _install_ocr(monkeypatch, type_texts, [('LV.1',)] * 6)

    rivals = read_rival_ships(object())

    assert rivals[0].ship_type is ShipType.CVL


def test_unknown_ship_type_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """枚举外的文本（含错字）不猜舰种。"""
    _install_ocr(monkeypatch, [('航亩',)] + [('航母',)] * 5, [('LV.1',)] * 6)

    rivals = read_rival_ships(object())

    assert rivals[0].ship_type is None


@pytest.mark.parametrize(
    ('level_text', 'expected'),
    [
        ('LV.110', 110),
        ('LV. 100', 100),
        ('110', 110),
        ('LV.', None),
        ('', None),
    ],
)
def test_level_takes_first_number(
    monkeypatch: pytest.MonkeyPatch,
    level_text: str,
    expected: int | None,
) -> None:
    """等级取文本里的第一段数字，没有数字时为空。"""
    _install_ocr(monkeypatch, [('航母',)] * 6, [(level_text,)] * 6)

    rivals = read_rival_ships(object())

    assert rivals[0].level == expected
