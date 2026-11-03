"""模块功能：验证普通换船主流程的分支与最终快照。

直接调用方：项目测试运行器。

直接依赖：fleet_select.models.normal。

边界：识别入口、舰队切换与船池动作全部换成替身，不截图、不点真机。
"""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.application.controller.types import ShipType
from autowsgr.application.fleet_select.models import normal as normal_module
from autowsgr.application.fleet_select.models.normal import adjust_normal_fleet
from autowsgr.application.fleet_select.operation import member_align as alignment_module
from autowsgr.application.fleet_select.types import FleetSnapshot


def _snapshot(names: tuple[str | None, ...]) -> FleetSnapshot:
    """用舰名拼一份六槽快照，占用状态按舰名是否为空推导。"""
    return FleetSnapshot(
        names=names,
        occupied=tuple(name is not None for name in names),
    )


def _empty() -> FleetSnapshot:
    """返回空编队快照。"""
    return _snapshot((None,) * 6)


def _filled() -> FleetSnapshot:
    """返回只有第 1 槽有船的快照。"""
    return _snapshot(('企业', None, None, None, None, None))


def _patch_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: list[FleetSnapshot],
) -> None:
    """按顺序返回固定快照，并让补读入口原样返回、不触发截图。"""
    queue = list(snapshots)

    def _next(_ctx: Any, **_kwargs: Any) -> FleetSnapshot:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(normal_module, 'read_fleet_snapshot', _next)
    monkeypatch.setattr(alignment_module, 'read_fleet_snapshot', _next)
    monkeypatch.setattr(
        normal_module,
        'read_missing_details',
        lambda _ctx, snapshot, **_kwargs: snapshot,
    )


def _patch_team(monkeypatch: pytest.MonkeyPatch, team: int | None) -> list[int]:
    """固定当前舰队编号，并记录真正发生的切队请求。"""
    clicks: list[int] = []

    def _switch(_ctx: Any, fleet_id: int | None) -> None:
        if fleet_id is not None and fleet_id != team:
            clicks.append(fleet_id)

    monkeypatch.setattr(normal_module, 'select_team', _switch)
    return clicks


def test_adjust_returns_immediately_when_fleet_already_matches(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前编队已经满足规则时不进船池。"""
    _patch_snapshots(monkeypatch, [_filled()])
    _patch_team(monkeypatch, 1)
    selected: list[int] = []
    monkeypatch.setattr(
        alignment_module,
        'select_ship',
        lambda *_args, **_kwargs: selected.append(1) or '企业',
    )

    snapshot = adjust_normal_fleet(ctx, fleet_rules=('企业', None, None, None, None, None))

    assert snapshot.names == ['企业', None, None, None, None, None]
    assert selected == []


def test_adjust_selects_missing_ship_then_returns_filled_fleet(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空槽会进船池补船，补完重新截图后返回。"""
    _patch_snapshots(monkeypatch, [_empty(), _filled()])
    _patch_team(monkeypatch, 1)
    requested: list[tuple[int, tuple[str, ...]]] = []
    monkeypatch.setattr(
        alignment_module,
        'select_ship',
        lambda _ctx, *, slot, selectors, **_: (
            requested.append(
                (slot, tuple(selector.name for selector in selectors)),
            )
            or '企业'
        ),
    )

    snapshot = adjust_normal_fleet(ctx, fleet_rules=('企业', None, None, None, None, None))

    assert requested == [(1, ('企业',))]
    assert snapshot.names == ['企业', None, None, None, None, None]


def test_adjust_switches_to_requested_fleet(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目标舰队与当前不同时先点对应标签页。"""
    clicks = _patch_team(monkeypatch, 1)
    _patch_snapshots(monkeypatch, [_filled()])
    monkeypatch.setattr(alignment_module, 'select_ship', lambda *_args, **_kwargs: '企业')

    adjust_normal_fleet(ctx, fleet_rules=('企业', None, None, None, None, None), fleet_id=3)

    assert clicks == [3]


def test_adjust_keeps_current_fleet_when_already_selected(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前已经是目标舰队时不重复点击。"""
    clicks = _patch_team(monkeypatch, 2)
    _patch_snapshots(monkeypatch, [_filled()])

    adjust_normal_fleet(ctx, fleet_rules=('企业', None, None, None, None, None), fleet_id=2)

    assert clicks == []


def test_adjust_rejects_out_of_range_fleet(ctx: Any) -> None:
    """舰队编号越界时在读页面之前就报错。"""
    with pytest.raises(ValueError, match='舰队编号必须在 1 到 4 之间'):
        adjust_normal_fleet(ctx, fleet_rules=('企业',), fleet_id=5)


def test_adjust_rejects_empty_first_slot_of_first_fleet(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 队第 1 个槽位不允许留空。"""
    _patch_team(monkeypatch, 1)

    with pytest.raises(ValueError, match='1 队第 1 个槽位不能为空'):
        adjust_normal_fleet(ctx, fleet_rules=(None,) * 6, fleet_id=1)


def test_adjust_pads_missing_rules_with_empty_slots(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只写一个舰名时，其余槽位按空槽补齐。"""
    _patch_snapshots(monkeypatch, [_filled()])

    snapshot = adjust_normal_fleet(ctx, fleet_rules=('企业',))

    assert snapshot.names == ['企业', None, None, None, None, None]


def test_adjust_rejects_too_many_rules(ctx: Any) -> None:
    """规则超过六个槽位时直接报错。"""
    with pytest.raises(ValueError, match='编队规则最多 6 个槽位'):
        adjust_normal_fleet(ctx, fleet_rules=('企业',) * 7)


def test_adjust_returns_none_when_rules_cannot_be_satisfied(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """规则本身无解时不读页面，直接返回空结果交给上层降级。"""
    _patch_team(monkeypatch, 1)

    assert adjust_normal_fleet(ctx, fleet_rules=('企业',) * 6) is None


def test_adjust_returns_none_after_retry_limit(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三轮修正都未通过校验时返回空结果，而不是抛异常。"""
    _patch_snapshots(monkeypatch, [_empty()])
    _patch_team(monkeypatch, 1)
    monkeypatch.setattr(
        alignment_module.FleetAligner, 'execute_member_plan', lambda *_a, **_k: None
    )
    monkeypatch.setattr(alignment_module.FleetAligner, 'execute_member_fix', lambda *_a, **_k: None)
    monkeypatch.setattr(
        alignment_module.FleetAligner, 'execute_member_reorder', lambda *_a, **_k: None
    )

    assert adjust_normal_fleet(ctx, fleet_rules=('企业',)) is None


def test_adjust_walks_snapshot_levels_until_details_resolve(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """快照始终缺舰种等级时，LEVEL2、LEVEL3、LEVEL4 各补读一帧。"""
    _patch_snapshots(monkeypatch, [_filled()])
    calls: list[bool] = []

    def _fill(_ctx: Any, snapshot: FleetSnapshot, **kwargs: Any) -> FleetSnapshot:
        calls.append(kwargs.get('detail_requirements') is not None)
        return snapshot

    monkeypatch.setattr(normal_module, 'read_missing_details', _fill)

    adjust_normal_fleet(ctx, fleet_rules=('企业',))

    assert calls == [False, False, True]


def test_adjust_skips_level3_when_snapshot_is_complete(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LEVEL2 已拿到全部字段时跳过 LEVEL3，只留 LEVEL4 的定向补读。"""
    complete = FleetSnapshot(
        names=('企业', None, None, None, None, None),
        occupied=(True, False, False, False, False, False),
        ship_types=(ShipType.CV, None, None, None, None, None),
        ship_levels=(110, None, None, None, None, None),
    )
    _patch_snapshots(monkeypatch, [complete])
    calls: list[bool] = []

    def _fill(_ctx: Any, snapshot: FleetSnapshot, **kwargs: Any) -> FleetSnapshot:
        calls.append(kwargs.get('detail_requirements') is not None)
        return snapshot

    monkeypatch.setattr(normal_module, 'read_missing_details', _fill)

    adjust_normal_fleet(ctx, fleet_rules=('企业',))

    assert calls == [False, True]


def test_adjust_reports_validation_and_result_events(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次编队判断与最终结果各上报一次，契约与旧版一致。"""
    _patch_snapshots(monkeypatch, [_filled()])
    events: list[tuple[str, dict[str, object]]] = []

    adjust_normal_fleet(
        ctx,
        fleet_rules=('企业', None, None, None, None, None),
        notify=lambda event, data: events.append((event, data)),
    )

    assert events == [
        ('fleet_validation', {'passed': True, 'members': ['企业', None, None, None, None, None]}),
        ('fleet_result', {'members': ['企业', None, None, None, None, None], 'passed': True}),
    ]
