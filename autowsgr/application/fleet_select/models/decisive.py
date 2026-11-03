"""模块功能：编排决战准备页的无搜索框换船流程。

上层调用：
- fleet_select.service：DECISIVE 模式的换船分发到这里。

下层依赖：
- fleet_select.operation.fleet_snapshot：读当前编队与最终位置。
- fleet_select.operation.ship_select：点对点选船与清空。
- fleet_select.operation.member_align：按目标顺序拖拽排序。
- fleet_select.rules.constraints：规则归一化与舰名比对。
- fleet_select.rules.planner：目标分配、成员匹配与校验。
- application.errors：换船失败时抛出具体操作错误。

边界：只编排决战流程，不识别页面、不点击坐标、不判断用哪种模式。

业务顺序：全局分配目标 → 读当前编队 → 尽量保留队内已有舰船 → 逐个补齐空位 →
倒序清空多余舰船 → 拖拽排序 → 重新截图验证；验证不过最多再做两次。
决战准备页没有搜索框，选船必须走不用搜索框的分支；它也是唯一允许拖拽排序的模式。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.errors import ActionFailedError
from autowsgr.application.fleet_select.constants import (
    ACTION_WAIT,
    MAX_SET_RETRIES,
    RETRY_WAIT,
)
from autowsgr.application.fleet_select.models.progress import report_progress
from autowsgr.application.fleet_select.operation.fleet_snapshot import (
    build_finished_snapshot,
    build_merged_snapshot,
    read_fleet_snapshot,
)
from autowsgr.application.fleet_select.operation.member_align import FleetAligner
from autowsgr.application.fleet_select.operation.ship_select import remove_ship, select_ship
from autowsgr.application.fleet_select.rules import constraints, planner
from autowsgr.application.fleet_select.types import (
    FLEET_SLOT_COUNT,
    FleetSlotRule,
    FleetSnapshot,
    ShipSelector,
)
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.models.decisive')


# ── 主流程 ──────────────────────────────────────────────────────────────────


def adjust_decisive_fleet(
    ctx: ContextHandle,
    *,
    fleet_rules: Sequence[FleetSlotRule | str | None],
    notify: Callable[[str, dict[str, object]], None] | None = None,
) -> FleetSnapshot:
    """把决战准备页舰队调整成目标编成。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        fleet_rules: 逐槽规则，可以只写舰名；不足六槽的按空槽补齐。
        notify: 换船过程中每完成一个动作时的上报回调。

    Returns:
        调整完成后的舰队快照。

    Raises:
        ValueError: 决战编队第一个槽位被要求留空。
        ActionFailedError: 目标编成无解，或多次修正后仍不满足规则。
    """
    selectors = constraints.normalize_rules(fleet_rules)
    if selectors[0] is None:
        raise ValueError('决战编队一号位不能为空')

    assigned = planner.plan_target_options(selectors)
    if assigned is None or assigned[0] is None:
        _log.error('[FLEET] 编队 → 拒绝：决战编队规则无法分配一号位，结果=未开始')
        raise ActionFailedError('调整舰队', '决战编队规则无法分配一号位')

    pool = planner.build_target_pool(selectors)
    initial = read_fleet_snapshot(ctx, expected_pool=pool)
    current = list(initial.names)
    occupied = list(initial.occupied)
    verified_slots: set[int] = set()
    target_members = planner.get_target_names(assigned)
    _log.debug('[FLEET] 编队 → 读取当前：members={!r}', current)
    _log.info('[FLEET] 编队 → 生成目标：目标成员={!r}', target_members)
    report_progress(
        notify,
        'fleet_validation',
        {
            'passed': planner.is_assignment_satisfied(current, occupied, assigned, verified_slots),
            'members': list(current),
        },
    )

    for attempt in range(MAX_SET_RETRIES + 1):
        if planner.is_assignment_satisfied(current, occupied, assigned, verified_slots):
            return _report_finished(current, occupied, initial)

        matched = _select_for_empty_slots(ctx, current, occupied, target_members, selectors, notify)
        _remove_extra_members(ctx, current, occupied, matched, notify)
        _execute_member_reorder(ctx, current, occupied, assigned, selectors, verified_slots, notify)

        fresh = read_fleet_snapshot(ctx, expected_pool=pool)
        current, occupied = build_merged_snapshot(current, fresh)
        if planner.is_assignment_satisfied(current, occupied, assigned, verified_slots):
            return _report_finished(current, occupied, initial)

        if attempt < MAX_SET_RETRIES:
            _log.debug(
                '[FLEET] 校验 → 未通过：attempt={}, max_attempts={}，下一步=重新规划',
                attempt + 1,
                MAX_SET_RETRIES + 1,
            )
            time.sleep(RETRY_WAIT)

    _log.error(
        '[FLEET] 编队 → 失败：attempt={}, max_attempts={}，决战编队重试后仍未满足目标规则，结果=未通过',
        MAX_SET_RETRIES + 1,
        MAX_SET_RETRIES + 1,
    )
    raise ActionFailedError('调整舰队', '决战编队重试后仍未满足目标规则')


# ── 成员补齐与排序 ──────────────────────────────────────────────────────────


def _select_for_empty_slots(
    ctx: ContextHandle,
    current: list[str | None],
    occupied: list[bool],
    target_members: Sequence[str | None],
    selectors: Sequence[FleetSlotRule | None],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> list[bool]:
    """沿用队内已有舰船，把还缺的目标逐槽选进空位。

    Args:
        ctx: dispatch 上下文句柄。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        target_members: 目标六槽舰名。
        selectors: 逐槽规则。
        notify: 进度回调。

    Returns:
        当前六槽中哪些位置可以保留。

    Raises:
        ActionFailedError: 目标舰船多到没有空槽可放。
    """
    matched, matched_slots = planner.match_existing_members(current, target_members, selectors)
    for target_slot, name in enumerate(target_members):
        if name is None or target_slot in matched_slots:
            continue
        slot = next((index for index in range(FLEET_SLOT_COUNT) if not matched[index]), None)
        if slot is None:
            raise ActionFailedError('调整舰队', f'决战没有可用槽位: {name}')

        option = constraints.get_option_for_name(name, selectors[target_slot]) or ShipSelector(
            name=name
        )
        previous_name = current[slot]
        selected = select_ship(ctx, slot=slot + 1, selectors=[option], use_search=False)
        current[slot] = selected or name
        occupied[slot] = True
        matched[slot] = True
        matched_slots.add(target_slot)
        _log.debug(
            '[FLEET] 换船 → 选中：slot={}, selected={!r}, previous={!r}',
            slot + 1,
            current[slot],
            previous_name,
        )
        report_progress(
            notify,
            'fleet_checkpoint',
            {'stage': 'selected', 'slot': slot + 1, 'members': list(current)},
        )
        time.sleep(ACTION_WAIT)
    return matched


def _remove_extra_members(
    ctx: ContextHandle,
    current: list[str | None],
    occupied: list[bool],
    matched: Sequence[bool],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> None:
    """倒序清空不在目标里的舰船，避免清空过程中出现空编队。

    Args:
        ctx: dispatch 上下文句柄。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        matched: 目标中可保留的槽位，来自 `_select_for_empty_slots`。
        notify: 进度回调。
    """
    for slot in range(FLEET_SLOT_COUNT - 1, -1, -1):
        if matched[slot] or not occupied[slot]:
            continue
        previous_name = current[slot]
        remove_ship(ctx, slot=slot + 1)
        current[slot] = None
        occupied[slot] = False
        _log.debug(
            '[FLEET] 换船 → 清空：slot={}, previous={!r}',
            slot + 1,
            previous_name,
        )
        report_progress(
            notify,
            'fleet_checkpoint',
            {'stage': 'cleared', 'slot': slot + 1, 'members': list(current)},
        )
        time.sleep(ACTION_WAIT)


def _execute_member_reorder(
    ctx: ContextHandle,
    current: list[str | None],
    occupied: list[bool],
    assigned: Sequence[ShipSelector | None],
    selectors: Sequence[FleetSlotRule | None],
    verified_slots: set[int],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> None:
    """按目标顺序从左到右拖拽舰船。

    Args:
        ctx: dispatch 上下文句柄。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        assigned: 目标六槽选船配置。
        selectors: 逐槽规则。
        verified_slots: 已通过 strict 校验的槽位，会被原地更新。
        notify: 进度回调。
    """
    FleetAligner(
        ctx=ctx,
        selectors=selectors,
        use_search=False,
        notify=notify,
        current=current,
        occupied=occupied,
        assigned=list(assigned),
        verified_slots=verified_slots,
    ).execute_member_reorder()


def _report_finished(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    initial: FleetSnapshot,
) -> FleetSnapshot:
    """打印最终编队并合成调用方要的完成快照。

    Args:
        current: 最终六槽舰名。
        occupied: 最终六槽占用情况。
        initial: 首次识别得到的快照，用于补回未重新识别的槽位。

    Returns:
        调整完成后的舰队快照。
    """
    _log.info('[FLEET] 编队 → 完成：当前成员={!r}，结果=通过', list(current))
    return build_finished_snapshot(current, occupied, initial)


__all__ = ['adjust_decisive_fleet']
