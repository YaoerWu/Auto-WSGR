"""模块功能：执行战役准备页的固定物理槽位编队调整。

上层调用：
- formation.fleet_adjustment.workflow：按 task_type 分派战役编队流程。
- business.combat.campaign：校验未配置具体舰名的战役舰种要求。

下层依赖：
- fleet_adjustment.workflow：提供识别、规划、单槽位选择和最终验证入口。
- common.fleet、common.types：提供规范化舰队规则和舰种类型。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.fleet_adjustment import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.ui.controller.fleet.formation.fleet_adjustment import (
        FleetAdjustment,
    )
    from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import (
        FleetSnapshot,
    )
    from autowsgr.application.ui.ships.types import ShipType
    from autowsgr.business.combat.fleet_models import FleetSlotRule, ShipSelector


_log = get_logger('ui.fleet.formation.fleet_adjustment')


def adjust_campaign_fleet(
    adjustment: FleetAdjustment,
    fleet_id: int | None,
    ship_names: Sequence[FleetSlotRule | str | None],
    *,
    reset_fleet: bool = True,
    on_event: Callable[..., None] | None = None,
    recognize_ship_types: bool = True,
) -> FleetSnapshot:
    """在战役准备页按固定物理槽位完成编队调整。"""
    if len(ship_names) > 6:
        raise ValueError('战役编队最多包含 6 个槽位')
    if (
        fleet_id is not None
        and adjustment._page.read_selected_fleet(adjustment._ctrl.screenshot()) != fleet_id
    ):
        adjustment._page.select_fleet(fleet_id)
        time.sleep(constants.FLEET_SWITCH_WAIT)

    _set_event_handler(adjustment, on_event)
    selectors = adjustment._normalize_selectors(ship_names)
    selectors += [None] * (6 - len(selectors))
    return _run_campaign_adjustment(
        adjustment,
        selectors,
        reset_fleet=reset_fleet,
        recognize_ship_types=recognize_ship_types,
    )


def validate_campaign_fleet(
    adjustment: FleetAdjustment,
    required_types: Sequence[ShipType],
    *,
    validate_types: bool = True,
) -> bool:
    """校验未配置具体舰名的战役当前编队。"""
    if not 1 <= len(required_types) <= 6:
        raise ValueError('战役舰种规则必须包含 1-6 个槽位')
    snapshot = adjustment._read_fleet_snapshot(
        recognize_ship_details=validate_types,
    )
    ship_types = snapshot.ship_types or []
    passed = all(
        snapshot.occupied[slot] and (not validate_types or ship_types[slot] is expected)
        for slot, expected in enumerate(required_types)
    ) and all(not occupied for occupied in snapshot.occupied[len(required_types) :])
    _log.info(
        '[Fleet] 战役舰种校验: 目标={} 当前={} 结果={}',
        [item.value for item in required_types],
        [item.value if item is not None else None for item in ship_types],
        '通过' if passed else '不通过',
    )
    return passed


def _run_campaign_adjustment(
    adjustment: FleetAdjustment,
    selectors: list[FleetSlotRule | None],
    *,
    reset_fleet: bool,
    recognize_ship_types: bool,
) -> FleetSnapshot:
    """执行战役固定槽位的识别、点对点替换和复查。"""
    if selectors[0] is None:
        raise ValueError('战役编队一号位不能为空')

    assigned = adjustment._plan_target_options(selectors)
    if assigned is None or assigned[0] is None:
        raise RuntimeError('战役编队规则无法分配一号位')

    expected_pool = adjustment._ocr_target_pool(selectors)
    snapshot = adjustment._detect_initial_snapshot(
        expected_pool,
        selectors,
        recognize_ship_types=recognize_ship_types,
    )
    current = list(snapshot.names)
    occupied = list(snapshot.occupied)
    verified_slots: set[int] = set()
    adjustment._initial_snapshot = snapshot
    adjustment._mark_snapshot_verified_slots(snapshot, assigned, verified_slots)
    adjustment._emit_fleet_event(
        'fleet_validation',
        passed=adjustment._validate_assignment(current, occupied, assigned, verified_slots),
        members=list(current),
    )

    if reset_fleet:
        _clear_campaign_fleet(adjustment, current, occupied)
        verified_slots.clear()

    for attempt in range(constants.MAX_SET_RETRIES + 1):
        if adjustment._validate_assignment(current, occupied, assigned, verified_slots):
            return _finish_campaign_fleet(adjustment, current, occupied, assigned, verified_slots)

        _replace_campaign_slots(
            adjustment,
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
        )
        names = adjustment._target_names(assigned)
        current, occupied = adjustment._detect_position_snapshot(
            current,
            names,
            stage='战役最终位置',
            round_number=attempt + 1,
        )
        if adjustment._validate_assignment(current, occupied, assigned, verified_slots):
            return _finish_campaign_fleet(adjustment, current, occupied, assigned, verified_slots)
        if attempt < constants.MAX_SET_RETRIES:
            time.sleep(constants.RETRY_WAIT)

    adjustment._log_final_result(
        current,
        occupied,
        assigned,
        verified_slots,
        passed=False,
    )
    raise RuntimeError('战役编队未能满足目标规则')


def _clear_campaign_fleet(
    adjustment: FleetAdjustment,
    current: list[str | None],
    occupied: list[bool],
) -> None:
    """清空当前六个物理槽位，不压缩剩余成员。"""
    for slot in range(5, -1, -1):
        if occupied[slot] or current[slot] is not None:
            _clear_campaign_slot(adjustment, slot, current, occupied)


def _replace_campaign_slots(
    adjustment: FleetAdjustment,
    current: list[str | None],
    occupied: list[bool],
    assigned: list[ShipSelector | None],
    selectors: list[FleetSlotRule | None],
    verified_slots: set[int],
) -> None:
    """先释放跨槽位重复目标，再逐物理槽位替换或清空。"""
    for target_slot, option in enumerate(assigned):
        if option is None:
            continue
        source_slot = next(
            (
                slot
                for slot, name in enumerate(current)
                if slot != target_slot
                and occupied[slot]
                and adjustment._option_matches_name(name, option)
            ),
            None,
        )
        if source_slot is not None:
            _clear_campaign_slot(adjustment, source_slot, current, occupied)

    for slot, option in enumerate(assigned):
        if option is None:
            if occupied[slot] or current[slot] is not None:
                _clear_campaign_slot(adjustment, slot, current, occupied)
            continue
        if _campaign_slot_satisfied(adjustment, slot, current, occupied, option, verified_slots):
            continue
        _select_campaign_slot(
            adjustment,
            slot,
            option,
            selectors[slot],
            current,
            occupied,
            assigned,
            verified_slots,
        )


def _select_campaign_slot(
    adjustment: FleetAdjustment,
    slot: int,
    option: ShipSelector,
    selector: FleetSlotRule | None,
    current: list[str | None],
    occupied: list[bool],
    assigned: list[ShipSelector | None],
    verified_slots: set[int],
) -> None:
    """按战役槽位规则执行一次点对点选船。"""
    if selector is None:
        raise RuntimeError(f'战役槽位 {slot + 1} 缺少选船规则')
    options = (option, *[candidate for candidate in selector.options if candidate != option])
    previous = current[slot]
    selected = adjustment._change_single_ship(
        slot,
        option.name,
        selector=options,
        slot_occupied=occupied[slot],
    )
    selected_option = next(
        (
            candidate
            for candidate in options
            if adjustment._option_matches_name(selected, candidate)
        ),
        None,
    )
    if selected is None or selected_option is None:
        raise RuntimeError(f'战役槽位 {slot + 1} 未选到目标舰船: {option.name}')
    current[slot] = selected
    occupied[slot] = True
    assigned[slot] = selected_option
    verified_slots.discard(slot)
    if adjustment._requires_selection_validation(selected_option):
        verified_slots.add(slot)
    _log.info('[Fleet] 战役点对点换船: 槽位{} {} -> {}', slot + 1, previous or '空槽', selected)
    adjustment._emit_fleet_event(
        'fleet_checkpoint',
        stage='selected',
        slot=slot + 1,
        members=list(current),
    )
    time.sleep(constants.ACTION_WAIT)


def _clear_campaign_slot(
    adjustment: FleetAdjustment,
    slot: int,
    current: list[str | None],
    occupied: list[bool],
) -> None:
    """清空战役准备页的一个固定物理槽位。"""
    previous = current[slot]
    adjustment._change_single_ship(slot, None, slot_occupied=occupied[slot])
    current[slot] = None
    occupied[slot] = False
    _log.info('[Fleet] 战役点对点清空: 槽位{} {} -> 空槽', slot + 1, previous or '未知舰船')
    adjustment._emit_fleet_event(
        'fleet_checkpoint',
        stage='cleared',
        slot=slot + 1,
        members=list(current),
    )
    time.sleep(constants.ACTION_WAIT)


def _campaign_slot_satisfied(
    adjustment: FleetAdjustment,
    slot: int,
    current: Sequence[str | None],
    occupied: Sequence[bool],
    option: ShipSelector,
    verified_slots: set[int],
) -> bool:
    """判断战役物理槽位是否已经满足目标规则。"""
    return (
        occupied[slot]
        and adjustment._option_matches_name(current[slot], option)
        and (not adjustment._requires_selection_validation(option) or slot in verified_slots)
    )


def _finish_campaign_fleet(
    adjustment: FleetAdjustment,
    current: list[str | None],
    occupied: list[bool],
    assigned: list[ShipSelector | None],
    verified_slots: set[int],
) -> FleetSnapshot:
    """记录战役编队成功并返回最终事实。"""
    adjustment._log_final_result(
        current,
        occupied,
        assigned,
        verified_slots,
        passed=True,
    )
    snapshot = adjustment._initial_snapshot
    return type(snapshot)(
        names=list(current),
        occupied=list(occupied),
        ship_types=snapshot.ship_types if snapshot is not None else None,
        ship_levels=snapshot.ship_levels if snapshot is not None else None,
    )


def _set_event_handler(
    adjustment: FleetAdjustment,
    on_event: Callable[..., None] | None,
) -> None:
    """更新本次战役流程的事件出口。"""
    adjustment._on_fleet_event = on_event
    adjustment._alignment._on_fleet_event = on_event


__all__ = ['adjust_campaign_fleet', 'validate_campaign_fleet']
