"""模块功能：编排普通出征、活动与演习的换船主流程。

上层调用：
- fleet_select.service：NORMAL 模式的换船分发到这里。

下层依赖：
- fleet_select.rules.constraints：逐槽规则归一化与名称比对。
- fleet_select.rules.planner：目标分配、校验、槽位定位与补船顺序。
- fleet_select.operation.team_select：切换 1 到 4 队舰队标签。
- fleet_select.operation.member_align：成员补齐、清空与拖拽排序。
- fleet_select.operation.fleet_snapshot：读快照、补读缺字段与合并最终位置。
- fleet_select.models.progress：向上层播报校验与终态。

边界：只编排已经规划好的换船步骤，不识别页面、不点击坐标、不判断用哪种模式。

业务顺序：切舰队 → 全局分配目标 → 四轮读当前编队 → 按现状重新分配 →
补齐成员 → 拖拽排序 → 重新截图验证；验证不过最多再做两次局部修正。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.fleet_select.constants import MAX_SET_RETRIES, RETRY_WAIT
from autowsgr.application.fleet_select.models.progress import report_progress
from autowsgr.application.fleet_select.operation.fleet_snapshot import (
    DetailRequirement,
    build_finished_snapshot,
    build_merged_snapshot,
    read_fleet_snapshot,
    read_missing_details,
)
from autowsgr.application.fleet_select.operation.member_align import (
    FleetAligner,
    UnresolvedPrimaryError,
)
from autowsgr.application.fleet_select.operation.team_select import select_team
from autowsgr.application.fleet_select.rules import constraints, planner
from autowsgr.application.fleet_select.rules.shipnames import get_ship_name_identity
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


_log = get_logger('fleet_select.models.normal')


# ── 主流程 ──────────────────────────────────────────────────────────────────


def adjust_normal_fleet(
    ctx: ContextHandle,
    *,
    fleet_rules: Sequence[FleetSlotRule | str | None],
    fleet_id: int | None = None,
    notify: Callable[[str, dict[str, object]], None] | None = None,
) -> FleetSnapshot | None:
    """把准备页舰队调整成目标编成，并复查最终位置。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        fleet_rules: 逐槽规则，可以只写舰名；不足六槽的按空槽补齐。
        fleet_id: 目标舰队编号 1-4；为空表示沿用当前舰队。
        notify: 换船过程中每完成一个动作时的上报回调。

    Returns:
        调整完成后的舰队快照；目标编成无解或主选最终无法确认时返回 None。

    Raises:
        ValueError: 舰队编号越界，或 1 队第 1 个槽位被要求留空。
    """
    selectors = constraints.normalize_rules(fleet_rules)
    select_team(ctx, fleet_id)

    # 先按规则做一次分配，规则本身无解时不必读页面。
    planned = planner.plan_target_options(selectors)
    if planned is None:
        _log.error('[FLEET] 编队 → 拒绝：目标编队无法满足主选和同舰唯一约束，结果=未开始')
        return None
    if fleet_id == 1 and planned[0] is None:
        raise ValueError('1 队第 1 个槽位不能为空')

    pool = planner.build_target_pool(selectors)
    snapshot = _read_initial_snapshot(ctx, selectors, pool)
    current = list(snapshot.names)
    occupied = list(snapshot.occupied)
    _log.debug('[FLEET] 编队 → 读取当前：members={!r}', current)

    # 带现状重新分配：在现有成员基础上选换船数最少的方案。
    assigned = planner.plan_target_options(selectors, current)
    if assigned is None:
        _log.error('[FLEET] 编队 → 拒绝：当前舰队无法分配为主选优先的不重名编成，结果=未开始')
        return None
    _log.info('[FLEET] 编队 → 生成目标：目标成员={!r}', planner.get_target_names(assigned))

    verified_slots = planner.build_snapshot_verified_slots(snapshot, assigned)
    aligner = FleetAligner(
        ctx=ctx,
        selectors=selectors,
        notify=notify,
        current=current,
        occupied=occupied,
        assigned=assigned,
        verified_slots=verified_slots,
    )
    initial_valid = _is_fleet_valid(aligner)
    _log.debug('[FLEET] 校验 → 初始检查：passed={}', initial_valid)
    report_progress(notify, 'fleet_validation', {'passed': initial_valid, 'members': current})

    deferred_primary_slots = planner.build_deferred_primary_slots(snapshot, selectors, assigned)

    for attempt in range(MAX_SET_RETRIES + 1):
        if _is_fleet_valid(aligner):
            return _report_finished(aligner, snapshot, notify)

        names = planner.get_target_names(assigned)
        try:
            _adjust_members_for_reorder(aligner, attempt, deferred_primary_slots, snapshot)
        except UnresolvedPrimaryError as error:
            _log.error(
                '[FLEET] 编队 → 失败：error_type={!r}, error={!r}，结果=未开始',
                type(error).__name__,
                str(error),
            )
            _report_failure(aligner)
            return None

        aligner.execute_member_reorder()

        # 重新截图确认最终位置，识别不到的槽位保留已确认舰名。
        aligner.current, aligner.occupied = _read_position_snapshot(
            ctx,
            aligner.current,
            names,
            stage='最终位置',
            round_number=attempt + 1,
        )
        if _is_fleet_valid(aligner):
            return _report_finished(aligner, snapshot, notify)

        if attempt < MAX_SET_RETRIES:
            _log.debug(
                '[FLEET] 校验 → 未通过：attempt={}, max_attempts={}，下一步=重新规划',
                attempt + 1,
                MAX_SET_RETRIES + 1,
            )
            time.sleep(RETRY_WAIT)
            aligner.current, aligner.occupied = _read_position_snapshot(
                ctx,
                aligner.current,
                names,
                stage='局部修正前',
                round_number=attempt + 2,
            )
        else:
            _log.error(
                '[FLEET] 编队 → 失败：attempt={}, max_attempts={}，结果=未开始',
                MAX_SET_RETRIES + 1,
                MAX_SET_RETRIES + 1,
            )
            _report_failure(aligner)

    return None


# ── 初始快照识别与细节校验 ──────────────────────────────────────────────────


def _read_initial_snapshot(
    ctx: ContextHandle,
    selectors: Sequence[FleetSlotRule | None],
    pool: Sequence[str],
) -> FleetSnapshot:
    """用四轮独立截图累计舰队信息，只补仍未确认的字段。

    LEVEL1 全局识别舰名并检测血条；LEVEL2 用新截图补舰名并首次识别全部有船
    槽位的舰种、等级，不符合 strict 规则的字段视为未确认；LEVEL3 再补一次；
    LEVEL4 最后补舰名，并只补主选或纯备选规则实际需要的舰种、等级。

    Args:
        ctx: 任务上下文句柄。
        selectors: 该模式的槽位规则；None 表示该槽位要求空槽。
        pool: 本次编成允许出现的舰名，用于纠正 OCR 近形字。

    Returns:
        四轮识别累计后的编队快照。
    """
    _log.debug('[FLEET] 识别 → 开始：level=1 读取全局舰名与槽位占用')
    snapshot = read_fleet_snapshot(ctx, expected_pool=pool, include_details=False)
    _report_snapshot('LEVEL1', snapshot, selectors)

    _log.debug('[FLEET] 识别 → 开始：level=2 补读舰名、舰种与等级')
    snapshot = read_missing_details(ctx, snapshot, expected_pool=pool)
    snapshot = _clear_invalid_strict_details(snapshot, selectors, stage='LEVEL2')
    _report_snapshot('LEVEL2', snapshot, selectors)

    if snapshot.has_unknown_details:
        _log.debug(
            '[FLEET] 识别 → 开始：level=3, name_slots={}, type_slots={}, level_slots={}',
            [slot + 1 for slot in snapshot.unknown_slots],
            [slot + 1 for slot in snapshot.unknown_type_slots],
            [slot + 1 for slot in snapshot.unknown_level_slots],
        )
        snapshot = read_missing_details(ctx, snapshot, expected_pool=pool)
        snapshot = _clear_invalid_strict_details(snapshot, selectors, stage='LEVEL3')
        _report_snapshot('LEVEL3', snapshot, selectors)
    else:
        _log.debug('[FLEET] 识别 → 跳过：level=3 LEVEL2 已取得全部字段')

    _log.debug(
        '[FLEET] 识别 → 开始：level=4, name_slots={}',
        [slot + 1 for slot in snapshot.unknown_slots],
    )
    snapshot = read_missing_details(
        ctx,
        snapshot,
        expected_pool=pool,
        detail_requirements=_build_level4_detail_requirements(selectors),
    )
    _report_snapshot('LEVEL4', snapshot, selectors)
    return snapshot


def _report_snapshot(
    stage: str,
    snapshot: FleetSnapshot,
    selectors: Sequence[FleetSlotRule | None],
) -> None:
    """记录一轮 OCR 合并后未通过的槽位；全通过时不打日志。

    Args:
        stage: 识别轮次，例如 LEVEL1。
        snapshot: 本轮合并后的编队快照。
        selectors: 该模式的槽位规则；None 表示该槽位要求空槽。
    """
    for slot, selector in enumerate(selectors):
        reason = _get_slot_match_reason(snapshot, slot, selector)
        if reason == '通过':
            continue
        _log.debug(
            '[FLEET] 识别 → 槽位未通过：stage={!r}, slot={}, occupied={}, name={!r}, reason={}',
            stage,
            slot + 1,
            snapshot.occupied[slot],
            snapshot.names[slot],
            reason,
        )


def _get_slot_match_reason(
    snapshot: FleetSnapshot,
    slot: int,
    selector: FleetSlotRule | None,
) -> str:
    """说明一个 OCR 槽位与同位置规则的匹配结果。

    Args:
        snapshot: 当前编队快照。
        slot: 槽位下标，0 基。
        selector: 该槽位的规则；None 表示要求空槽。

    Returns:
        以「通过」或「不通过: 原因」开头的说明文字。
    """
    name = snapshot.names[slot]
    is_occupied = snapshot.occupied[slot]
    if selector is None:
        return '通过' if not is_occupied and name is None else '不通过: 规则要求空槽'
    if not is_occupied:
        return '不通过: 槽位为空'
    if name is None:
        return '不通过: 舰名未识别'
    option = next(
        (
            candidate
            for candidate in selector.options
            if constraints.is_option_name_matched(name, candidate)
        ),
        None,
    )
    if option is None:
        return '不通过: 舰名不匹配'
    return _get_option_match_reason(snapshot, slot, option)


def _get_option_match_reason(
    snapshot: FleetSnapshot,
    slot: int,
    option: ShipSelector,
) -> str:
    """说明已匹配舰名的舰种、等级是否满足一条规则。

    Args:
        snapshot: 当前编队快照。
        slot: 槽位下标，0 基。
        option: 已按舰名匹配上的选船配置。

    Returns:
        以「通过」或「不通过: 原因」开头的说明文字。
    """
    if option.relaxed_constraints:
        return '通过: relaxed仅校验舰名'
    ship_type = snapshot.ship_types[slot] if snapshot.ship_types else None
    ship_level = snapshot.ship_levels[slot] if snapshot.ship_levels else None
    if option.ship_types and ship_type not in option.ship_types:
        detail = '未识别' if ship_type is None else f'{ship_type.value}不满足规则'
        return f'不通过: 舰种{detail}'
    if (option.min_level is not None or option.max_level is not None) and ship_level is None:
        return '不通过: 等级未识别'
    if option.min_level is not None and ship_level < option.min_level:
        return f'不通过: 等级{ship_level}低于{option.min_level}'
    if option.max_level is not None and ship_level > option.max_level:
        return f'不通过: 等级{ship_level}高于{option.max_level}'
    return '通过'


def _build_level4_detail_requirements(
    selectors: Sequence[FleetSlotRule | None],
) -> dict[str, DetailRequirement]:
    """返回 LEVEL4 仍需要补舰种、等级的舰名身份。

    有主选的槽位只保留主选：识别成备选的船必然会被换掉，不必再补细节。
    纯备选槽没有主选，仍需按被选中的备选自身约束完成校验。

    Args:
        selectors: 该模式的槽位规则；None 表示该槽位要求空槽。

    Returns:
        舰名身份到「需要舰种、需要等级」的映射。
    """
    requirements: dict[str, DetailRequirement] = {}
    for selector in selectors:
        if selector is None:
            continue
        options = (selector.primary,) if selector.primary is not None else selector.candidates
        for option in options:
            identity = get_ship_name_identity(option.name)
            if identity is None:
                continue
            previous = requirements.get(identity, DetailRequirement(False, False))
            requirements[identity] = DetailRequirement(
                previous.require_ship_type or bool(option.ship_types),
                previous.require_ship_level
                or option.min_level is not None
                or option.max_level is not None,
            )
    return requirements


def _clear_invalid_strict_details(
    snapshot: FleetSnapshot,
    selectors: Sequence[FleetSlotRule | None],
    *,
    stage: str,
) -> FleetSnapshot:
    """把不符合 strict 规则的舰种、等级标记为未确认，留给下一阶段重识别。

    Args:
        snapshot: 当前编队快照。
        selectors: 该模式的槽位规则；None 表示该槽位要求空槽。
        stage: 识别轮次，只用于日志。

    Returns:
        细节字段可能被清空的编队快照。
    """
    requirements: dict[str, list[ShipSelector]] = {}
    for selector in selectors:
        if selector is None:
            continue
        options = (selector.primary,) if selector.primary is not None else selector.candidates
        for option in options:
            if option.relaxed_constraints:
                continue
            identity = get_ship_name_identity(option.name)
            if identity is not None:
                requirements.setdefault(identity, []).append(option)

    ship_types: list[ShipType | None] = list(snapshot.ship_types or (None,) * FLEET_SLOT_COUNT)
    ship_levels: list[int | None] = list(snapshot.ship_levels or (None,) * FLEET_SLOT_COUNT)
    changed = False
    for slot, name in enumerate(snapshot.names):
        options = requirements.get(get_ship_name_identity(name) or '')
        if not options:
            continue

        type_options = [option for option in options if option.ship_types]
        ship_type = ship_types[slot]
        if (
            ship_type is not None
            and type_options
            and not any(ship_type in option.ship_types for option in type_options)
        ):
            _log.debug(
                '[FLEET] 校验 → 丢弃舰种：stage={!r}, slot={}, ship_type={!r}, 不符合 strict 规则',
                stage,
                slot + 1,
                ship_type.value if ship_type is not None else None,
            )
            ship_types[slot] = None
            changed = True

        level_options = [
            option
            for option in options
            if option.min_level is not None or option.max_level is not None
        ]
        ship_level = ship_levels[slot]
        if (
            ship_level is not None
            and level_options
            and not any(
                (option.min_level is None or ship_level >= option.min_level)
                and (option.max_level is None or ship_level <= option.max_level)
                for option in level_options
            )
        ):
            _log.debug(
                '[FLEET] 校验 → 丢弃等级：stage={!r}, slot={}, ship_level={}, 不符合 strict 规则',
                stage,
                slot + 1,
                ship_level,
            )
            ship_levels[slot] = None
            changed = True

    if not changed:
        return snapshot
    return FleetSnapshot(
        names=snapshot.names,
        occupied=snapshot.occupied,
        ship_types=tuple(ship_types),
        ship_levels=tuple(ship_levels),
    )


# ── 成员调整与最终校验 ──────────────────────────────────────────────────────


def _adjust_members_for_reorder(
    aligner: FleetAligner,
    attempt: int,
    deferred_primary_slots: set[int],
    initial_snapshot: FleetSnapshot,
) -> None:
    """确保目标成员齐全：齐全时直接排序，否则先完整对齐或局部修正。

    Args:
        aligner: 当前对齐状态。
        attempt: 当前重试轮次，0 表示首次调整。
        deferred_primary_slots: 主选留到局部修正阶段的槽位。
        initial_snapshot: 首次识别得到的快照，用于恢复被覆盖的槽位信息。
    """
    if planner.is_member_set_satisfied(
        aligner.current,
        aligner.occupied,
        aligner.assigned,
        aligner.verified_slots,
    ):
        _log.debug('[FLEET] 编队 → 跳过换船：目标成员已齐全')
        return
    if attempt == 0:
        aligner.execute_member_plan(
            deferred_primary_slots=deferred_primary_slots,
            initial_snapshot=initial_snapshot,
        )
    else:
        _log.debug('[FLEET] 编队 → 局部修正：attempt={}', attempt)
        aligner.execute_member_fix(initial_snapshot=initial_snapshot)


def _read_position_snapshot(
    ctx: ContextHandle,
    current: Sequence[str | None],
    names: Sequence[str | None],
    *,
    stage: str,
    round_number: int,
) -> tuple[list[str | None], list[bool]]:
    """记录并执行一轮最终位置 OCR，合并已确认的舰名。

    Args:
        ctx: 任务上下文句柄。
        current: 调整前的槽位舰名。
        names: 目标舰名，用于纠正 OCR 近形字。
        stage: 本次识别所处阶段，只用于日志。
        round_number: 识别轮次，只用于日志。

    Returns:
        合并后的槽位舰名与槽位占用。
    """
    _log.debug(
        '[FLEET] 识别 → 开始：stage={!r}, round={}, max_rounds={}',
        stage,
        round_number,
        MAX_SET_RETRIES + 1,
    )
    fresh = read_fleet_snapshot(ctx, expected_slot_names=names)
    merged, occupied = build_merged_snapshot(current, fresh)
    _log.debug(
        '[FLEET] 识别 → 后处理：stage={!r}, round={}, current={}, occupied={}, target={}',
        stage,
        round_number,
        merged,
        occupied,
        names,
    )
    return merged, occupied


def _is_fleet_valid(aligner: FleetAligner) -> bool:
    """判断当前编队是否已经满足目标规则。

    Args:
        aligner: 当前对齐状态。

    Returns:
        编队是否已满足全部槽位规则。
    """
    return planner.is_assignment_satisfied(
        aligner.current,
        aligner.occupied,
        aligner.assigned,
        aligner.verified_slots,
    )


def _report_finished(
    aligner: FleetAligner,
    initial: FleetSnapshot,
    notify: Callable[[str, dict[str, object]], None] | None,
) -> FleetSnapshot:
    """打印最终编队，并合成调用方要的完成快照。

    Args:
        aligner: 当前对齐状态。
        initial: 首次识别得到的快照，用于补回未重新识别的槽位。
        notify: 进度回调；None 表示不回报。

    Returns:
        调整完成后的编队快照。
    """
    names = list(aligner.current)
    _log.info('[FLEET] 编队 → 完成：当前成员={!r}，结果=通过', names)
    report_progress(notify, 'fleet_result', {'members': names, 'passed': True})
    return build_finished_snapshot(names, aligner.occupied, initial)


def _report_failure(aligner: FleetAligner) -> None:
    """统一输出最终编队和未通过校验的逐槽原因。

    Args:
        aligner: 当前对齐状态。
    """
    reasons: list[str] = []
    identities = [
        identity
        for name in aligner.current
        if (identity := get_ship_name_identity(name)) is not None
    ]
    if len(identities) != len(set(identities)):
        reasons.append('舰队中存在同名舰船')

    for slot, option in enumerate(aligner.assigned):
        name = aligner.current[slot]
        if option is None:
            if aligner.occupied[slot] or name is not None:
                reasons.append(f'槽位{slot + 1}应为空，实际为{name or "未知舰船"}')
            continue
        if not aligner.occupied[slot]:
            reasons.append(f"槽位{slot + 1}为空，目标为'{option.name}'")
        elif name is None:
            reasons.append(f"槽位{slot + 1}舰名未识别，目标为'{option.name}'")
        elif not constraints.is_option_name_matched(name, option):
            reasons.append(f"槽位{slot + 1}当前为'{name}'，目标为'{option.name}'")
        elif constraints.should_validate_selection(option) and slot not in aligner.verified_slots:
            reasons.append(f"槽位{slot + 1}的'{name}'未通过 strict 舰种或等级校验")
    _log.error(
        '[FLEET] 编队 → 校验失败：members={!r}, reasons={!r}，结果=未通过',
        list(aligner.current),
        reasons or ['最终校验未通过'],
    )


__all__ = ['adjust_normal_fleet']
