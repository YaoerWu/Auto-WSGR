"""模块功能：验证出征准备页舰队识别的读取流程。

直接调用方：项目测试运行器。

直接依赖：pytest、ship_recognition.checker 与 common.vision 的识别模型。

边界：用替身接管 OCR 与像素识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import (
    ShipDamage,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import (
    checker as ship_checker,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.constants import (
    BLOOD_BAR_PROBES,
    BLOOD_SIGNATURES,
    FLEET_SLOT_COUNT,
    SHIP_LEVEL_ROIS,
    SHIP_NAME_ROIS,
    SHIP_TYPE_ROIS,
)
from autowsgr.common.vision import RecognitionProfile, TextDetection


def _group(*texts: str) -> list[TextDetection]:
    """把若干文本包成单个区域的识别结果。"""
    return [TextDetection(recognized_text=text, confidence_score=0.9) for text in texts]


def _install_text_frame(
    monkeypatch: pytest.MonkeyPatch,
    groups: list[list[TextDetection]],
) -> list[dict[str, object]]:
    """让一次 OCR 读帧返回六个区域的识别结果，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=True, observation=groups)

    monkeypatch.setattr(ship_checker, 'expect_ocr', expect_ocr)
    return calls


def _install_damage_frame(
    monkeypatch: pytest.MonkeyPatch,
    signatures: list[str | None],
) -> list[dict[str, object]]:
    """让一次像素读帧返回六个探针的命中候选名，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_pixels(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(
            satisfied=True,
            observation=[SimpleNamespace(matched_signature=value) for value in signatures],
        )

    monkeypatch.setattr(ship_checker, 'expect_pixels', expect_pixels)
    return calls


_TEXT_READERS = [
    pytest.param(ship_checker.read_ship_types, SHIP_TYPE_ROIS, id='types'),
    pytest.param(ship_checker.read_ship_levels, SHIP_LEVEL_ROIS, id='levels'),
    pytest.param(ship_checker.read_ship_names, SHIP_NAME_ROIS, id='names'),
]


# ── 血条状态 ────────────────────────────────────────────────────────────────


def test_ship_damage_values() -> None:
    """血条状态对外使用稳定的英文枚举值。"""
    assert [damage.value for damage in ShipDamage] == [
        'no_ship',
        'normal',
        'moderate',
        'severe',
    ]


def test_read_ship_damage_maps_one_frame_to_six_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次像素读帧把六个探针按画面顺序映射为六个槽位状态。"""
    calls = _install_damage_frame(
        monkeypatch,
        ['normal', 'no_ship', 'moderate', 'severe', None, 'severe'],
    )

    assert ship_checker.read_ship_damage(object()) == [
        ShipDamage.NORMAL,
        ShipDamage.NO_SHIP,
        ShipDamage.MODERATE,
        ShipDamage.SEVERE,
        None,
        ShipDamage.SEVERE,
    ]
    assert calls[0]['signature'] is BLOOD_SIGNATURES
    assert calls[0]['attempts'] == 1


def test_blood_signatures_cover_six_slots() -> None:
    """每条组合签名对应一个槽位，探针坐标与公开常量一致。"""
    assert len(BLOOD_SIGNATURES) == FLEET_SLOT_COUNT

    for slot, signature in enumerate(BLOOD_SIGNATURES, start=1):
        assert signature.name == f'slot_{slot}'
        candidates = [candidate.name for candidate in signature.signatures]
        assert candidates == ['normal', 'no_ship', 'moderate', 'severe', 'severe']
        rule = signature.signatures[0].rules[0]
        assert (rule.x, rule.y) == BLOOD_BAR_PROBES[slot - 1]


# ── 舰种 / 等级 / 舰名文字 ──────────────────────────────────────────────────


@pytest.mark.parametrize(('reader', 'roi'), _TEXT_READERS)
def test_text_reader_reads_one_frame_of_six_slots(
    monkeypatch: pytest.MonkeyPatch,
    reader: object,
    roi: object,
) -> None:
    """三个文字入口各自一次读帧，区域与识别参数固定，结果顺序与画面一致。"""
    calls = _install_text_frame(monkeypatch, [_group(f'文字{slot}') for slot in range(1, 7)])

    assert reader(object()) == [f'文字{slot}' for slot in range(1, 7)]
    assert calls[0]['roi'] is roi
    assert calls[0]['recognition_profile'] is RecognitionProfile.SINGLE_LINE
    assert calls[0]['attempts'] == 1


@pytest.mark.parametrize(('reader', '_roi'), _TEXT_READERS)
def test_text_reader_folds_blank_groups_and_keeps_raw_first_text(
    monkeypatch: pytest.MonkeyPatch,
    reader: object,
    _roi: object,
) -> None:
    """整组空白折成 None；有文字时取第一条原文，不 strip、不加工。"""
    groups = [
        _group('', ' '),
        _group(' 轻母(U国) '),
        _group('', 'LV.110'),
        _group(),
        _group('企业'),
        _group(' '),
    ]
    _install_text_frame(monkeypatch, groups)

    assert reader(object()) == [None, ' 轻母(U国) ', 'LV.110', None, '企业', None]


def test_text_readers_keep_their_own_regions(monkeypatch: pytest.MonkeyPatch) -> None:
    """三个入口互不串台：各读各的区域，返回值保留 OCR 原文。"""
    text = ['航母', '轻母(U国)', '战列', '潜艇', '驱逐', '重巡']
    _install_text_frame(monkeypatch, [_group(value) for value in text])

    assert ship_checker.read_ship_types(object()) == text
    assert ship_checker.read_ship_levels(object()) == text
    assert ship_checker.read_ship_names(object()) == text
