"""模块功能：验证换船对齐的成员补齐、清空与拖拽排序。

直接调用方：项目测试运行器。

直接依赖：fleet_select.alignment 与换船规则模型。

边界：换船与清空动作换成替身，不打开船池；拖拽只验证坐标与顺序同步。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    CLICK_SHIP_SLOTS,
    DRAG_DURATION_SECONDS,
)
from autowsgr.application.fleet_select import alignment as alignment_module
from autowsgr.application.fleet_select.alignment import FleetAligner, find_deferred_primary_slots
from autowsgr.application.fleet_select.models import FleetSlotRule, FleetSnapshot, ShipSelector


if TYPE_CHECKING:
    import pytest


def _rule(name: str, *candidates: str) -> FleetSlotRule:
    """构造一条带备选的槽位规则。"""
    return FleetSlotRule(
        primary=ShipSelector(name=name),
        candidates=tuple(ShipSelector(name=candidate) for candidate in candidates),
    )


def _aligner(
    ctx: Any,
    *,
    current: tuple[str | None, ...],
    occupied: tuple[bool, ...],
    assigned: tuple[ShipSelector | None, ...],
    selectors: tuple[FleetSlotRule | None, ...] = (None,) * 6,
    notify: Any = None,
) -> FleetAligner:
    """按给定的编队事实搭一个对齐器。"""
    return FleetAligner(
        ctx=ctx,
        selectors=selectors,
        notify=notify,
        current=list(current),
        occupied=list(occupied),
        assigned=list(assigned),
    )


def test_find_deferred_primary_slots_marks_unknown_primary() -> None:
    """已占用但舰名未知、规划上仍是主选的槽位需要先进兜底流程。"""
    selectors: tuple[FleetSlotRule | None, ...] = (_rule('企业'), None, None, None, None, None)
    snapshot = FleetSnapshot(
        names=(None, None, None, None, None, None),
        occupied=(True, False, False, False, False, False),
    )

    slots = find_deferred_primary_slots(snapshot, selectors, (selectors[0].primary, *([None] * 5)))

    assert slots == {0}


def test_find_deferred_primary_slots_ignores_known_names() -> None:
    """舰名已经识别出来的槽位是常规流程，不进兜底。"""
    selectors: tuple[FleetSlotRule | None, ...] = (_rule('企业'), None, None, None, None, None)
    snapshot = FleetSnapshot(
        names=('企业', None, None, None, None, None),
        occupied=(True, False, False, False, False, False),
    )

    slots = find_deferred_primary_slots(snapshot, selectors, (selectors[0].primary, *([None] * 5)))

    assert slots == set()


def test_align_fleet_does_nothing_when_members_already_match(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成员已经齐全时不进船池。"""
    selected: list[str] = []
    monkeypatch.setattr(
        alignment_module,
        'select_ship',
        lambda *_args, **_kwargs: selected.append('unexpected') or '企业',
    )
    aligner = _aligner(
        ctx,
        current=('企业', None, None, None, None, None),
        occupied=(True, False, False, False, False, False),
        assigned=(ShipSelector(name='企业'), None, None, None, None, None),
    )

    aligner.align_fleet()

    assert selected == []


def test_align_fleet_removes_extra_member_from_tail(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目标成员齐全后，多余成员从后往前删掉。"""
    removed: list[int] = []
    monkeypatch.setattr(
        alignment_module,
        'remove_ship',
        lambda _ctx, *, slot: removed.append(slot),
    )
    monkeypatch.setattr(alignment_module, 'select_ship', lambda *_args, **_kwargs: None)
    aligner = _aligner(
        ctx,
        current=('企业', '突击者', None, None, None, None),
        occupied=(True, True, False, False, False, False),
        assigned=(ShipSelector(name='企业'), None, None, None, None, None),
    )

    aligner.align_fleet()

    assert removed == [2]
    assert aligner.current == ['企业', None, None, None, None, None]
    assert aligner.occupied == [True, False, False, False, False, False]


def test_align_fleet_reports_selected_ship(ctx: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """换掉一艘船之后同步内存状态并上报事件。"""
    monkeypatch.setattr(alignment_module, 'select_ship', lambda *_args, **_kwargs: '企业')
    events: list[tuple[str, dict[str, object]]] = []
    aligner = _aligner(
        ctx,
        current=(None,) * 6,
        occupied=(False,) * 6,
        assigned=(ShipSelector(name='企业'), None, None, None, None, None),
        notify=lambda event, data: events.append((event, data)),
    )

    aligner.align_fleet()

    assert aligner.current[0] == '企业'
    assert events == [('ship_selected', {'slot': 1, 'selected': '企业'})]


def test_reorder_fleet_drags_ship_to_target_position(ctx: Any) -> None:
    """目标顺序与当前顺序不同时，把船从源槽位拖到目标槽位。"""
    events: list[tuple[str, dict[str, object]]] = []
    aligner = _aligner(
        ctx,
        current=('甲', '乙', '丙', None, None, None),
        occupied=(True, True, True, False, False, False),
        assigned=(
            ShipSelector(name='丙'),
            ShipSelector(name='甲'),
            ShipSelector(name='乙'),
            None,
            None,
            None,
        ),
        notify=lambda event, data: events.append((event, data)),
    )

    aligner.reorder_fleet()

    assert ctx.runtime.ctrl.swipes == [
        (*CLICK_SHIP_SLOTS[2], *CLICK_SHIP_SLOTS[0], DRAG_DURATION_SECONDS),
    ]
    assert aligner.current[:3] == ['丙', '甲', '乙']
    assert events == [('ship_moved', {'source': 3, 'destination': 1})]


def test_reorder_fleet_skips_ship_missing_from_fleet(ctx: Any) -> None:
    """目标舰船不在队里时只记警告，不产生无效拖拽。"""
    aligner = _aligner(
        ctx,
        current=('甲', None, None, None, None, None),
        occupied=(True, False, False, False, False, False),
        assigned=(ShipSelector(name='丁'), None, None, None, None, None),
    )

    aligner.reorder_fleet()

    assert ctx.runtime.ctrl.swipes == []
