"""模块功能：验证快速整备识别的调用契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.sortie.battle_preparation.quick_maintenance 与 vision 识别入口。

边界：用替身接管模板加载和识别入口，不读取模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller.sortie.battle_preparation import quick_maintenance
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance import (
    checker as quick_maintenance_checker,
)


@pytest.fixture(autouse=True)
def _stub_template_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """模板加载替身：不读图片，只保留文件名供断言。"""

    def load_template(filename: str) -> tuple[str, str]:
        return ('template', filename)

    monkeypatch.setattr(quick_maintenance_checker, '_load_template', load_template)


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    satisfied: bool,
    center: tuple[float, float] | None,
    calls: list[dict[str, object]],
) -> None:
    """用替身接管两个识别入口，并记下调用参数。"""

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=satisfied, observation=[])

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float] | None:
        calls.append(options)
        return center

    monkeypatch.setattr(quick_maintenance_checker, 'expect_template', expect_template)
    monkeypatch.setattr(quick_maintenance_checker, 'expect_template_center', expect_template_center)


@pytest.mark.parametrize(('satisfied', 'expected'), [(True, True), (False, False)])
def test_check_auto_supply_reports_the_match_result(
    monkeypatch: pytest.MonkeyPatch,
    satisfied: bool,
    expected: bool,
) -> None:
    """自动补给只认开启态模板：命中为真，没命中为假。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, satisfied=satisfied, center=None, calls=calls)

    assert quick_maintenance.check_auto_supply_enabled(object()) is expected
    assert len(calls) == 1
    assert calls[0]['template'] == ('template', quick_maintenance_checker.AUTO_SUPPLY_TEMPLATE)
    assert calls[0]['roi'] is quick_maintenance_checker.AUTO_SUPPLY_ROI


@pytest.mark.parametrize(('satisfied', 'expected'), [(True, True), (False, False)])
def test_check_quick_repair_requires_tab_and_all_repair_button(
    monkeypatch: pytest.MonkeyPatch,
    satisfied: bool,
    expected: bool,
) -> None:
    """修理视图要页签和「全部修理」按钮同时命中：两个模板一次识别。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, satisfied=satisfied, center=None, calls=calls)

    assert quick_maintenance.check_quick_repair_active(object()) is expected
    assert len(calls) == 1
    assert calls[0]['template'] == (
        ('template', quick_maintenance_checker.QUICK_REPAIR_TEMPLATE),
        ('template', quick_maintenance_checker.ALL_REPAIR_BUTTON_TEMPLATE),
    )
    assert calls[0]['roi'] == (
        quick_maintenance_checker.QUICK_REPAIR_ROI,
        quick_maintenance_checker.ALL_REPAIR_BUTTON_ROI,
    )
    assert calls[0]['min_matches'] == 2
    assert calls[0]['attempts'] == 4
    assert calls[0]['interval_seconds'] == 0.5


def test_read_auto_supply_center_returns_the_match_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """自动补给的落点直接取自命中模板中心。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, satisfied=True, center=(0.05, 0.93), calls=calls)

    assert quick_maintenance.read_auto_supply_center(object()) == (0.05, 0.93)
    assert calls[0]['roi'] is quick_maintenance_checker.AUTO_SUPPLY_ROI


def test_read_quick_repair_center_returns_none_when_not_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页签没命中时落点为空，交给调用方回退静态坐标。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, satisfied=False, center=None, calls=calls)

    assert quick_maintenance.read_quick_repair_center(object()) is None
    assert calls[0]['roi'] is quick_maintenance_checker.QUICK_REPAIR_ROI


def test_read_all_repair_center_returns_the_button_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """「全部修理」的落点取自按钮模板中心。"""
    calls: list[dict[str, object]] = []
    _install_recognition(monkeypatch, satisfied=True, center=(0.85, 0.68), calls=calls)

    assert quick_maintenance.read_all_repair_center(object()) == (0.85, 0.68)
    assert calls[0]['template'] == (
        'template',
        quick_maintenance_checker.ALL_REPAIR_BUTTON_TEMPLATE,
    )
    assert calls[0]['roi'] is quick_maintenance_checker.ALL_REPAIR_BUTTON_ROI


def _install_ocr_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    texts: tuple[str, ...],
    calls: list[dict[str, object]],
) -> None:
    """用替身接管 OCR 入口，按给定文本返回识别结果。"""

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(
            satisfied=bool(texts),
            observation=[
                SimpleNamespace(recognized_text=text, confidence_score=1.0, text_region=None)
                for text in texts
            ],
        )

    monkeypatch.setattr(quick_maintenance_checker, 'expect_ocr', expect_ocr)


@pytest.mark.parametrize(
    ('texts', 'expected'),
    [(('7188',), 7188), ((), None), (('',), None), (('7 188',), None)],
)
def test_read_repair_tool_count_returns_the_detected_number(
    monkeypatch: pytest.MonkeyPatch,
    texts: tuple[str, ...],
    expected: int | None,
) -> None:
    """工具存量只接受纯数字文本，其余一律给空。"""
    calls: list[dict[str, object]] = []
    _install_ocr_recognition(monkeypatch, texts=texts, calls=calls)

    assert quick_maintenance.read_repair_tool_count(object()) == expected
    assert calls[0]['roi'] is quick_maintenance_checker.REPAIR_STOCK_ROI
    assert calls[0]['allowlist'] == '0123456789'
    assert calls[0]['attempts'] == 1


def _install_pixel_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    matched_signatures: tuple[str | None, ...],
    calls: list[dict[str, object]],
) -> None:
    """用替身接管像素入口，按给定候选名逐槽返回命中结果。"""

    def expect_pixels(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        observation = [
            SimpleNamespace(matched=name is not None, matched_signature=name)
            for name in matched_signatures
        ]
        return SimpleNamespace(satisfied=True, observation=observation)

    monkeypatch.setattr(quick_maintenance_checker, 'expect_pixels', expect_pixels)


def test_read_ship_damage_maps_each_slot_to_its_reference_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """六个槽位各自按命中的参考色归类，未命中参考色的槽位为空。"""
    calls: list[dict[str, object]] = []
    _install_pixel_recognition(
        monkeypatch,
        matched_signatures=('normal', 'moderate', 'severe', 'no_ship', None, 'normal'),
        calls=calls,
    )

    damages = quick_maintenance.read_ship_damage(object())

    assert damages == {
        1: quick_maintenance.ShipDamage.NORMAL,
        2: quick_maintenance.ShipDamage.MODERATE,
        3: quick_maintenance.ShipDamage.SEVERE,
        4: quick_maintenance.ShipDamage.NO_SHIP,
        5: None,
        6: quick_maintenance.ShipDamage.NORMAL,
    }
    assert len(calls) == 1
    assert calls[0]['signature'] is quick_maintenance_checker._BLOOD_SIGNATURES
    assert calls[0]['attempts'] == 1


def test_blood_signatures_probe_one_rule_per_slot() -> None:
    """每个槽位一条组合签名，候选规则落在同序的血条探针位上。"""
    signatures = quick_maintenance_checker._BLOOD_SIGNATURES

    assert len(signatures) == len(quick_maintenance_checker.BLOOD_BAR_PROBES) == 6
    for slot, signature in enumerate(signatures, start=1):
        assert signature.name == f'slot_{slot}'
        assert len(signature.signatures) == len(quick_maintenance_checker._BLOOD_COLORS)
        for candidate in signature.signatures:
            rule = candidate.rules[0]
            assert (rule.x, rule.y) == quick_maintenance_checker.BLOOD_BAR_PROBES[slot - 1]
