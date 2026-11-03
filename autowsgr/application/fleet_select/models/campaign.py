"""模块功能：编排战役准备页的一槽一船替换流程。

上层调用：
- fleet_select.service：CAMPAIGN 模式的换船分发到这里。

下层依赖：
- fleet_select.operation.fleet_snapshot：读当前编队与最终位置。
- fleet_select.operation.ship_select：带搜索框选船与清空。
- fleet_select.rules.constraints：规则归一化、舰名比对与舰种校验。
- fleet_select.rules.planner：目标分配、占用记账与校验。
- application.errors：换船失败时抛出具体操作错误。

边界：只编排战役流程，不识别页面、不点击坐标、不判断用哪种模式。

业务顺序：全局分配目标 → 读当前编队并记下可强校验的槽位 → 需要重置时清空全部物理槽 →
逐槽替换成一船一坑 → 重新截图验证；验证不过最多再做两次。
战役准备页没有队伍页签，不能切换队伍，也没有拖拽排序；它只有一槽一船的替换能力。
"""

# TODO: 战役流程暂不重写，先按当前实现保持可用。后续把 check_campaign_fleet 的舰种
# 校验并入 adjust_campaign_fleet，与决战一样从普通模式裁剪得到，而不是独立一份实现。

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

    from autowsgr.application.controller.types import ShipType
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.models.campaign')


# ── 主流程 ──────────────────────────────────────────────────────────────────


def adjust_campaign_fleet(
    ctx: ContextHandle,
    *,
    fleet_rules: Sequence[FleetSlotRule | str | None],
    reset_fleet: bool = True,
    notify: Callable[[str, dict[str, object]], None] | None = None,
) -> FleetSnapshot:
    """把战役准备页舰队调整成目标编成。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        fleet_rules: 逐槽规则，可以只写舰名；不足六槽的按空槽补齐。
        reset_fleet: 调整前是否先清空全部物理槽位。
        notify: 换船过程中每完成一个动作时的上报回调。

    Returns:
        调整完成后的舰队快照。

    Raises:
        ValueError: 战役编队第一个槽位被要求留空。
        ActionFailedError: 目标编成无解，或多次修正后仍不满足规则。
    """
    selectors = constraints.normalize_rules(fleet_rules)
    if selectors[0] is None:
        raise ValueError('战役编队一号位不能为空')

    assigned = planner.plan_target_options(selectors)
    if assigned is None or assigned[0] is None:
        _log.error('[FLEET] 编队 → 拒绝：战役编队规则无法分配一号位，结果=未开始')
        raise ActionFailedError('调整舰队', '战役编队规则无法分配一号位')

    pool = planner.build_target_pool(selectors)
    initial = read_fleet_snapshot(ctx, expected_pool=pool)
    current = list(initial.names)
    occupied = list(initial.occupied)
    verified_slots = planner.build_snapshot_verified_slots(initial, assigned)
    _log.debug('[FLEET] 编队 → 读取当前：members={!r}', current)
    _log.info('[FLEET] 编队 → 生成目标：目标成员={!r}', planner.get_target_names(assigned))
    report_progress(
        notify,
        'fleet_validation',
        {
            'passed': planner.is_assignment_satisfied(current, occupied, assigned, verified_slots),
            'members': list(current),
        },
    )

    if reset_fleet:
        _remove_all_members(ctx, current, occupied, notify)
        verified_slots.clear()

    for attempt in range(MAX_SET_RETRIES + 1):
        if planner.is_assignment_satisfied(current, occupied, assigned, verified_slots):
            return _report_finished(current, occupied, initial)

        _execute_slot_replacements(
            ctx, current, occupied, assigned, selectors, verified_slots, notify
        )

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
        '[FLEET] 编队 → 失败：attempt={}, max_attempts={}，战役编队未能满足目标规则，结果=未通过',
        MAX_SET_RETRIES + 1,
        MAX_SET_RETRIES + 1,
    )
    raise ActionFailedError('调整舰队', '战役编队未能满足目标规则')


def _read_campaign_fleet_matched(
    ctx: ContextHandle,
    required_types: Sequence[ShipType],
    *,
    validate_types: bool = True,
) -> bool:
    """读取战役准备页并校验前几槽是否正好是要求的舰种。

    暂无调用方：等战役流程按模块顶部 TODO 并入 adjust_campaign_fleet 时启用。

    Args:
        ctx: 提供截图事实的 dispatch 上下文句柄。
        required_types: 从一号位开始逐槽要求的舰种。
        validate_types: 是否比对舰种，关闭后只要求这些槽位有船。

    Returns:
        前几槽符合要求且其后没有多余舰船时为真。

    Raises:
        ValueError: 要求的舰种数量不在 1 到 6 之间。
    """
    return constraints.is_campaign_types_matched(
        read_fleet_snapshot(ctx),
        required_types,
        validate_types=validate_types,
    )


# ── 槽位替换 ────────────────────────────────────────────────────────────────


def _remove_all_members(
    ctx: ContextHandle,
    current: list[str | None],
    occupied: list[bool],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> None:
    """倒序清空全部物理槽位，去掉旧编队留下的所有舰船。

    Args:
        ctx: dispatch 上下文句柄。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        notify: 进度回调。
    """
    for slot in range(FLEET_SLOT_COUNT - 1, -1, -1):
        if occupied[slot]:
            _remove_member(ctx, slot, current, occupied, notify)


def _execute_slot_replacements(
    ctx: ContextHandle,
    current: list[str | None],
    occupied: list[bool],
    assigned: list[ShipSelector | None],
    selectors: Sequence[FleetSlotRule | None],
    verified_slots: set[int],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> None:
    """先释放跨槽重复的舰船，再逐槽把每一坑换成一船。

    Args:
        ctx: dispatch 上下文句柄。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        assigned: 目标六槽选船配置，实际选中后会原地替换。
        selectors: 逐槽规则。
        verified_slots: 已通过 strict 校验的槽位，会被原地更新。
        notify: 进度回调。

    Raises:
        ActionFailedError: 槽位缺少选船规则，或选船后没落到目标舰船。
    """
    for target_slot, option in enumerate(assigned):
        if option is None:
            continue
        source = next(
            (
                slot
                for slot, name in enumerate(current)
                if slot != target_slot
                and occupied[slot]
                and constraints.is_option_name_matched(name, option)
            ),
            None,
        )
        if source is not None:
            _remove_member(ctx, source, current, occupied, notify)

    for slot, option in enumerate(assigned):
        if option is None:
            if occupied[slot] or current[slot] is not None:
                _remove_member(ctx, slot, current, occupied, notify)
            continue
        if (
            occupied[slot]
            and constraints.is_option_name_matched(current[slot], option)
            and (not constraints.should_validate_selection(option) or slot in verified_slots)
        ):
            continue

        selector = selectors[slot]
        if selector is None:
            raise ActionFailedError('调整舰队', f'战役槽位 {slot + 1} 缺少选船规则')
        options = (option, *(candidate for candidate in selector.options if candidate != option))
        selected = select_ship(ctx, slot=slot + 1, selectors=list(options), use_search=True)
        selected_option = next(
            (
                candidate
                for candidate in options
                if constraints.is_option_name_matched(selected, candidate)
            ),
            None,
        )
        if selected is None or selected_option is None:
            raise ActionFailedError(
                '调整舰队', f'战役槽位 {slot + 1} 未选到目标舰船: {option.name}'
            )

        previous_name = current[slot]
        current[slot] = selected
        occupied[slot] = True
        assigned[slot] = selected_option
        verified_slots.discard(slot)
        if constraints.should_validate_selection(selected_option):
            verified_slots.add(slot)
        _log.debug(
            '[FLEET] 换船 → 选中：slot={}, selected={!r}, previous={!r}',
            slot + 1,
            selected,
            previous_name,
        )
        report_progress(
            notify,
            'fleet_checkpoint',
            {'stage': 'selected', 'slot': slot + 1, 'members': list(current)},
        )
        time.sleep(ACTION_WAIT)


def _remove_member(
    ctx: ContextHandle,
    slot: int,
    current: list[str | None],
    occupied: list[bool],
    notify: Callable[[str, dict[str, object]], None] | None,
) -> None:
    """清空指定槽位。

    Args:
        ctx: dispatch 上下文句柄。
        slot: 槽位下标，0 基。
        current: 当前六槽舰名，会被原地更新。
        occupied: 当前六槽占用情况，会被原地更新。
        notify: 进度回调。
    """
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


__all__ = ['adjust_campaign_fleet']
