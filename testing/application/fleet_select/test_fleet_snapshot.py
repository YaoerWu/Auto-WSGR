"""模块功能：验证准备页识别原文到舰队事实的解析与三档舰名比对。

直接调用方：项目测试运行器。

直接依赖：fleet_select.snapshot 与 ship_recognition 的识别入口。

边界：四个识别入口用替身接管，不截图、不读模板。
"""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import (
    ShipDamage,
)
from autowsgr.application.controller.types import ShipType
from autowsgr.application.fleet_select.operation import fleet_snapshot as fleet_snapshot_module
from autowsgr.application.fleet_select.operation.fleet_snapshot import (
    build_finished_snapshot,
    read_fleet_snapshot,
)
from autowsgr.application.fleet_select.rules import ocr as ocr_module
from autowsgr.application.fleet_select.types import FleetSnapshot


@pytest.fixture(autouse=True)
def _fixed_shipname_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """把舰名表固定成一艘船，让三档比对互不干扰。"""
    monkeypatch.setattr(ocr_module, 'SHIPNAMES', ['企业'])


def _patch_recognition(
    monkeypatch: pytest.MonkeyPatch,
    name_texts: tuple[str | None, ...],
    *,
    type_texts: tuple[str | None, ...] = (None,) * 6,
    level_texts: tuple[str | None, ...] = (None,) * 6,
    no_ship_slots: tuple[int, ...] = (),
) -> None:
    """把四个识别入口换成固定原文；占用按血条替身给出。"""
    damage = [
        ShipDamage.NO_SHIP if index in no_ship_slots or text is None else ShipDamage.NORMAL
        for index, text in enumerate(name_texts)
    ]
    monkeypatch.setattr(fleet_snapshot_module, 'read_ship_damage', lambda _ctx: damage)
    monkeypatch.setattr(fleet_snapshot_module, 'read_ship_names', lambda _ctx: list(name_texts))
    monkeypatch.setattr(fleet_snapshot_module, 'read_ship_types', lambda _ctx: list(type_texts))
    monkeypatch.setattr(fleet_snapshot_module, 'read_ship_levels', lambda _ctx: list(level_texts))


def test_snapshot_matches_name_from_shipname_table(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第一档：舰名表里能直接对上的就采用。"""
    _patch_recognition(monkeypatch, ('企业', None, None, None, None, None))

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.names == ('企业', None, None, None, None, None)
    assert snapshot.occupied == (True, False, False, False, False, False)


def test_snapshot_falls_back_to_slot_target_name(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第二档：舰名表对不上时，只在本槽目标名里再比一次。"""
    _patch_recognition(monkeypatch, ('突击号', None, None, None, None, None))

    snapshot = read_fleet_snapshot(
        ctx,
        expected_slot_names=('突击者', None, None, None, None, None),
    )

    assert snapshot.names[0] == '突击者'


def test_snapshot_falls_back_to_target_pool(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第三档：没有逐槽目标时，在整个目标池里补救匹配。"""
    _patch_recognition(monkeypatch, ('突击号', None, None, None, None, None))

    snapshot = read_fleet_snapshot(ctx, expected_pool=['突击者'])

    assert snapshot.names[0] == '突击者'


def test_snapshot_leaves_unmatched_text_empty(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三档都匹配不上时不猜，槽位舰名留空。"""
    _patch_recognition(monkeypatch, ('完全无关的文字', None, None, None, None, None))

    snapshot = read_fleet_snapshot(ctx, expected_pool=['突击者'])

    assert snapshot.names[0] is None
    assert snapshot.occupied == (True, False, False, False, False, False)


def test_snapshot_keeps_unknown_slots_empty(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """识别不到舰名原文的空槽不参与比对。"""
    _patch_recognition(monkeypatch, (None,) * 6)

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.names == (None,) * 6
    assert snapshot.occupied == (False,) * 6


def test_snapshot_ignores_name_text_on_empty_slot(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """战役页空槽在舰名行写着「类型限定」，血条判空后不采信这段文字。"""
    _patch_recognition(
        monkeypatch,
        ('类型限定', None, None, None, None, None),
        no_ship_slots=(0,),
    )

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.names[0] is None
    assert snapshot.occupied[0] is False


def test_finished_snapshot_keeps_details_with_their_ship() -> None:
    """对齐会移动船，舰种与等级要按舰名身份回到新槽位，而不是照搬原槽位。"""
    initial = FleetSnapshot(
        names=['新奥尔良', '欧根亲王', '墨尔本', '维斯比', '南京', None],
        occupied=[True, True, True, True, True, False],
        ship_types=(ShipType.CA, ShipType.CA, ShipType.CVL, ShipType.DD, ShipType.CV, None),
        ship_levels=(10, 8, 9, 8, 110, None),
    )

    finished = build_finished_snapshot(
        ['新奥尔良', '墨尔本', '维斯比', '欧根亲王', '提康德罗加', None],
        [True, True, True, True, True, False],
        initial,
    )

    assert finished.ship_types == (ShipType.CA, ShipType.CVL, ShipType.DD, ShipType.CA, None, None)
    assert finished.ship_levels == (10, 9, 8, 8, None, None)


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('航母', ShipType.CV),
        ('轻母(U国)', ShipType.CVL),
        ('轻母（U国）', ShipType.CVL),
        ('  战列 (J国) ', ShipType.BB),
        ('航亩', None),
        ('', None),
        ('航母（J国）（U国）', None),
    ],
)
def test_snapshot_parses_ship_type(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    expected: ShipType | None,
) -> None:
    """舰种原文先剥国籍括号，再与枚举值全等匹配，不在枚举内视为未识别。"""
    _patch_recognition(
        monkeypatch,
        ('企业', None, None, None, None, None),
        type_texts=(text, None, None, None, None, None),
    )

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.ship_types[0] is expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('LV.110', 110),
        ('lv. 100', 100),
        ('LV.SO', 50),
        ('LV.I10', 110),
        ('LV. 1', 1),
        ('LV. 0', None),
        ('LV. 111', None),
        ('110', None),
        ('', None),
    ],
)
def test_snapshot_parses_level(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    expected: int | None,
) -> None:
    """等级只认 LV 前缀，形近字母归一后按 1-110 区间校验。"""
    _patch_recognition(
        monkeypatch,
        ('企业', None, None, None, None, None),
        level_texts=(text, None, None, None, None, None),
    )

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.ship_levels[0] == expected
