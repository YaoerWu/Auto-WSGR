"""模块功能：验证准备页识别原文到标准舰名的三档比对。

直接调用方：项目测试运行器。

直接依赖：fleet_select.snapshot 与 ship_recognition 的事实模型。

边界：识别入口用替身接管，不截图、不读模板。
"""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    FleetRecognition,
)
from autowsgr.application.fleet_select import snapshot as snapshot_module
from autowsgr.application.fleet_select.snapshot import read_fleet_snapshot


def _recognition(name_texts: tuple[str | None, ...]) -> FleetRecognition:
    """用舰名原文拼出一份六槽识别事实。"""
    return FleetRecognition(
        name_texts=name_texts,
        occupied=tuple(text is not None for text in name_texts),
        ship_types=(None,) * 6,
        ship_levels=(None,) * 6,
    )


@pytest.fixture(autouse=True)
def _fixed_shipname_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """把舰名表固定成一艘船，让三档比对互不干扰。"""
    monkeypatch.setattr(snapshot_module, 'SHIPNAMES', ['企业'])


def _patch_recognition(
    monkeypatch: pytest.MonkeyPatch,
    name_texts: tuple[str | None, ...],
) -> None:
    """把识别入口换成固定事实。"""
    monkeypatch.setattr(
        snapshot_module,
        'read_fleet_recognition',
        lambda _ctx: _recognition(name_texts),
    )


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
    _patch_recognition(monkeypatch, (None, None, None, None, None, None))

    snapshot = read_fleet_snapshot(ctx)

    assert snapshot.names == (None,) * 6
    assert snapshot.occupied == (False,) * 6
