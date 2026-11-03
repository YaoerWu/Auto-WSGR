"""模块功能：按舰队规则和当前事实计算唯一目标、下一步动作与校验结论。

上层调用：
- fleet_select.models：生成目标编成、判断是否收敛、决定下一轮做什么。
- fleet_select.operation.member_align：取下一步动作与重新规划结果。

下层依赖：
- fleet_select.rules.constraints：判断规则与舰船身份是否匹配。
- fleet_select.rules.shipnames：舰名归一化与身份比较。
- fleet_select.types：规则、快照与槽位数据契约。

边界：只做纯计算，不识别页面、不点击、不读写文件。

目标分配按主选优先、备选靠后的顺序做全局唯一分配，同一身份不得占用两个槽位，
优先复用队内已有舰船。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Literal

from autowsgr.application.fleet_select.rules import constraints
from autowsgr.application.fleet_select.rules.shipnames import (
    get_ship_name_identity,
    normalize_ship_name,
)
from autowsgr.application.fleet_select.types import FLEET_SLOT_COUNT
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.fleet_select.types import (
        FleetSlotRule,
        FleetSnapshot,
        ShipSelector,
    )


_log = get_logger('fleet_select.rules.planner')


# ── 计算状态与动作 ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class FleetState:
    """一轮换船过程中可变的编队事实。"""

    selectors: Sequence[FleetSlotRule | None]
    current: list[str | None]
    occupied: list[bool]
    assigned: list[ShipSelector | None]
    verified_slots: set[int] = field(default_factory=set)
    unavailable: set[tuple[int, ShipSelector]] = field(default_factory=set)
    locked: dict[int, ShipSelector] = field(default_factory=dict)
    attempted: set[tuple[int, ShipSelector, int]] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class MemberStep:
    """成员集合调整的下一步决策。"""

    kind: Literal['done', 'skip', 'replan', 'select']
    target_slot: int = 0
    ship_slot: int = 0
    option: ShipSelector | None = None


# ── 目标分配 ────────────────────────────────────────────────────────────────


def plan_target_options(
    selectors: Sequence[FleetSlotRule | None],
    current: Sequence[str | None] = (),
    unavailable: set[tuple[int, ShipSelector]] | frozenset[tuple[int, ShipSelector]] = frozenset(),
    locked: dict[int, ShipSelector] | None = None,
) -> list[ShipSelector | None] | None:
    """按主选优先级规划全局唯一的精确选船规则。

    Args:
        selectors: 逐槽规则，None 表示该槽留空。
        current: 当前六槽舰名，用于优先复用已在队内的舰船。
        unavailable: 已判定不可用的（零基槽位，规则）组合。
        locked: 已锁定不能改派的零基槽位与规则。

    Returns:
        逐槽精确规则；无可行分配时为 None。
    """
    locked = locked or {}
    current_identities = _get_current_identities(current)
    slot_options = _build_slot_options(selectors, current_identities, unavailable, locked)
    if slot_options is None:
        return None

    @cache
    def plan_slot_option(
        slot: int,
        used: tuple[str, ...],
    ) -> tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None:
        """回溯搜索从指定槽位开始的全局唯一分配。

        Args:
            slot: 当前处理的槽位下标。
            used: 已被占用的舰名身份。

        Returns:
            换船艘数、各槽名次与各槽规则的最优组合；无解时为 None。
        """
        if slot >= len(slot_options):
            return 0, (), ()

        best: tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None = None
        used_set = set(used)
        for rank, option in enumerate(slot_options[slot]):
            if option is None:
                result = plan_slot_option(slot + 1, used)
                identity = None
            else:
                identity = get_ship_name_identity(option.name)
                if identity is None or identity in used_set:
                    continue
                result = plan_slot_option(slot + 1, tuple(sorted((*used, identity))))
            if result is None:
                continue

            rest_cost, rest_priority, rest_assignment = result
            replacement_cost = 0 if option is None or identity in current_identities else 1
            candidate = (
                replacement_cost + rest_cost,
                (rank, *rest_priority),
                (option, *rest_assignment),
            )
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        return best

    result = plan_slot_option(0, ())
    return list(result[2]) if result is not None else None


def build_target_pool(selectors: Sequence[FleetSlotRule | None]) -> list[str]:
    """返回全部主选和备选组成的位置无关 OCR 上下文池。

    Args:
        selectors: 逐槽规则。

    Returns:
        去重后的标准舰名列表。
    """
    pool: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        if selector is None:
            continue
        for option in selector.options:
            normalized = normalize_ship_name(option.name)
            identity = get_ship_name_identity(normalized)
            if normalized is not None and identity is not None and identity not in seen:
                pool.append(normalized)
                seen.add(identity)
    return pool


def get_target_names(assigned: Sequence[ShipSelector | None]) -> list[str | None]:
    """把精确规则转换为最终逐槽使用的标准舰名。

    Args:
        assigned: 逐槽精确规则。

    Returns:
        与槽位对齐的标准舰名，空槽为 None。
    """
    return [normalize_ship_name(option.name) if option is not None else None for option in assigned]


# ── 分配结果校验 ────────────────────────────────────────────────────────────


def is_assignment_satisfied(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    assigned: Sequence[ShipSelector | None],
    verified_slots: set[int] | frozenset[int] = frozenset(),
) -> bool:
    """验证舰名、占用、位置、唯一性和严格选船记录。

    Args:
        current: 当前六槽舰名。
        occupied: 当前六槽是否占用。
        assigned: 逐槽精确规则。
        verified_slots: 已通过船池复核约束的零基槽位集合。

    Returns:
        全部槽位都满足分配结果时为 True。
    """
    identities = [
        identity for name in current if (identity := get_ship_name_identity(name)) is not None
    ]
    if len(identities) != len(set(identities)):
        return False

    for slot, option in enumerate(assigned):
        if option is None:
            if occupied[slot] or current[slot] is not None:
                return False
            continue
        if not occupied[slot] or not constraints.is_option_name_matched(current[slot], option):
            return False
        if constraints.should_validate_selection(option) and slot not in verified_slots:
            return False
    return True


def is_member_set_satisfied(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    assigned: Sequence[ShipSelector | None],
    verified_slots: set[int] | frozenset[int],
) -> bool:
    """判断目标成员是否齐全且没有额外成员，不检查舰船顺序。

    Args:
        current: 当前六槽舰名。
        occupied: 当前六槽是否占用。
        assigned: 逐槽精确规则。
        verified_slots: 已通过船池复核约束的零基槽位集合。

    Returns:
        成员集合完全一致时为 True。
    """
    protected, satisfied, _ = get_assignment_locations(
        current,
        occupied,
        assigned,
        verified_slots,
    )
    required_slots = {slot for slot, option in enumerate(assigned) if option is not None}
    member_slots = {
        slot
        for slot, (name, is_occupied) in enumerate(zip(current, occupied, strict=True))
        if is_occupied or name is not None
    }
    return satisfied == required_slots and protected == member_slots


def build_snapshot_verified_slots(
    snapshot: FleetSnapshot,
    assigned: Sequence[ShipSelector | None],
    verified_slots: set[int] | frozenset[int] = frozenset(),
) -> set[int]:
    """用首次快照标记已就位且满足规则的逻辑槽位，跳过选船二次确认。

    已确认无需更换的舰船不再进入点对点选船页更换，避免已就位舰船
    不在船池中导致选不到、重选、再选不到的循环。

    强校验：名称匹配后舰种与等级必须全部符合规则才标记，任一约束因
    OCR 缺失无法确认时也不标记，落入选船页权威校验。
    放宽约束的规则本就不要求选船校验，由赋值匹配直接放行。

    Args:
        snapshot: 首次截图得到的舰队快照。
        assigned: 逐槽精确规则。
        verified_slots: 已经确认过的零基槽位集合。

    Returns:
        本次快照确认后的零基槽位集合。
    """
    result = set(verified_slots)
    if snapshot.ship_types is None or snapshot.ship_levels is None:
        return result
    for target_slot, option in enumerate(assigned):
        if option is None or not constraints.should_validate_selection(option):
            continue
        if target_slot in result:
            continue
        position = next(
            (
                slot
                for slot in range(FLEET_SLOT_COUNT)
                if snapshot.occupied[slot]
                and constraints.is_option_name_matched(snapshot.names[slot], option)
            ),
            None,
        )
        if position is None:
            continue
        if not constraints.is_snapshot_satisfied_option(snapshot, position, option):
            _log.debug(
                '[FLEET] 校验 → 快照不通过：slot={}, name={!r}，下一步=进入选船页',
                target_slot + 1,
                snapshot.names[position],
            )
            continue
        result.add(target_slot)
        _log.debug(
            '[FLEET] 校验 → 快照确认：slot={}, name={!r}，结果=通过',
            target_slot + 1,
            snapshot.names[position],
        )
    return result


# ── 槽位定位 ────────────────────────────────────────────────────────────────


def match_existing_members(
    current: Sequence[str | None],
    desired: Sequence[str | None],
    selectors: Sequence[FleetSlotRule | None],
    verified_slots: set[int] | frozenset[int] = frozenset(),
) -> tuple[list[bool], set[int]]:
    """在当前舰队与目标槽位之间做一对一匹配。

    Args:
        current: 当前六槽舰名。
        desired: 目标六槽舰名。
        selectors: 逐槽规则。
        verified_slots: 已通过船池复核约束的零基槽位集合。

    Returns:
        ok: 当前六槽中哪些槽位上的舰船可以保留。
        matched_slots: 哪些目标槽位已由当前舰船满足。
    """
    ok: list[bool] = [False] * FLEET_SLOT_COUNT
    matched_slots: set[int] = set()
    used_positions: set[int] = set()
    target_slots = [slot for slot, name in enumerate(desired) if name is not None]

    def is_slot_taken_by(slot: int, ship: str | None) -> bool:
        """判断当前舰船是否已经满足该槽位的目标规则。

        Args:
            slot: 目标逻辑槽位，0 基。
            ship: 当前槽位上的舰名。

        Returns:
            舰名一致且约束校验通过时为 True。
        """
        selector = selectors[slot]
        option = constraints.get_option_for_name(desired[slot], selector)
        return (
            get_ship_name_identity(ship) == get_ship_name_identity(desired[slot])
            and (option is None or constraints.is_search_name_matched(ship, option.search_name))
            and (not constraints.should_validate_selection(option) or slot in verified_slots)
        )

    for slot in target_slots:
        if is_slot_taken_by(slot, current[slot]):
            ok[slot] = True
            matched_slots.add(slot)
            used_positions.add(slot)

    for slot in target_slots:
        if slot in matched_slots:
            continue
        for position, ship in enumerate(current):
            if position in used_positions:
                continue
            if is_slot_taken_by(slot, ship):
                ok[position] = True
                matched_slots.add(slot)
                used_positions.add(position)
                break

    return ok, matched_slots


def get_assignment_locations(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    assigned: Sequence[ShipSelector | None],
    verified_slots: set[int] | frozenset[int],
) -> tuple[set[int], set[int], dict[int, int]]:
    """定位当前成员对应的逻辑目标，并标记已满足目标。

    Args:
        current: 当前六槽舰名。
        occupied: 当前六槽是否占用。
        assigned: 逐槽精确规则。
        verified_slots: 已通过船池复核约束的零基槽位集合。

    Returns:
        protected: 已被目标占用的物理槽位。
        satisfied: 已满足且完成约束校验的逻辑槽位。
        target_positions: 逻辑槽位到物理槽位的映射。
    """
    protected: set[int] = set()
    satisfied: set[int] = set()
    target_positions: dict[int, int] = {}

    for target_slot, option in enumerate(assigned):
        if option is None:
            continue
        positions = [
            target_slot,
            *[slot for slot in range(FLEET_SLOT_COUNT) if slot != target_slot],
        ]
        position = next(
            (
                slot
                for slot in positions
                if slot not in protected
                and occupied[slot]
                and constraints.is_option_name_matched(current[slot], option)
            ),
            None,
        )
        if position is None:
            continue
        protected.add(position)
        target_positions[target_slot] = position
        if not constraints.should_validate_selection(option) or target_slot in verified_slots:
            satisfied.add(target_slot)

    return protected, satisfied, target_positions


def _get_target_order(
    assigned: Sequence[ShipSelector | None],
    selectors: Sequence[FleetSlotRule | None],
) -> list[int]:
    """按主选优先、其余按槽位顺序返回目标处理顺序。

    Args:
        assigned: 逐槽精确规则。
        selectors: 逐槽原始规则。

    Returns:
        需要补船的零基逻辑槽位顺序。
    """
    slots = [slot for slot, option in enumerate(assigned) if option is not None]
    return sorted(
        slots,
        key=lambda slot: (
            selectors[slot] is None
            or selectors[slot].primary is None
            or assigned[slot] != selectors[slot].primary,
            slot,
        ),
    )


def _get_replacement_slot(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    option: ShipSelector,
    protected: set[int],
    target_position: int | None,
    attempted: set[tuple[int, ShipSelector, int]],
    target_slot: int,
) -> int | None:
    """选择补船位置：原舰、空槽、多余舰、未知占用。

    Args:
        current: 当前六槽舰名。
        occupied: 当前六槽是否占用。
        option: 待补的选船规则。
        protected: 已被目标占用的物理槽位。
        target_position: 该逻辑槽位当前已占用的物理槽位。
        attempted: 已尝试过的（逻辑槽位，规则，物理槽位）组合。
        target_slot: 零基逻辑槽位。

    Returns:
        可补船的零基物理槽位；没有可用位置时为 None。
    """
    if target_position is not None:
        key = (target_slot, option, target_position)
        return target_position if key not in attempted else None

    empty_slots = [
        slot for slot in range(FLEET_SLOT_COUNT) if slot not in protected and not occupied[slot]
    ]
    extra_slots = [
        slot
        for slot in range(FLEET_SLOT_COUNT)
        if slot not in protected and occupied[slot] and current[slot] is not None
    ]
    normal_slots = [*empty_slots, *extra_slots]
    if normal_slots and not any((target_slot, option, slot) in attempted for slot in normal_slots):
        return normal_slots[0]

    return next(
        (
            slot
            for slot in range(FLEET_SLOT_COUNT)
            if slot not in protected
            and occupied[slot]
            and current[slot] is None
            and (target_slot, option, slot) not in attempted
        ),
        None,
    )


def build_deferred_primary_slots(
    snapshot: FleetSnapshot,
    selectors: Sequence[FleetSlotRule | None],
    assigned: Sequence[ShipSelector | None],
) -> set[int]:
    """定位身份未知、需要先进主选兜底流程的逻辑槽位。

    Args:
        snapshot: 首次截图得到的舰队快照。
        selectors: 逐槽原始规则。
        assigned: 逐槽精确规则。

    Returns:
        已占用但舰名未识别、且规划上仍是主选的零基逻辑槽位集合。
    """
    return {
        slot
        for slot, (name, is_occupied, selector, option) in enumerate(
            zip(snapshot.names, snapshot.occupied, selectors, assigned, strict=True),
        )
        if is_occupied
        and name is None
        and selector is not None
        and selector.primary is not None
        and option == selector.primary
    }


# ── 下一步动作 ──────────────────────────────────────────────────────────────


def plan_member_step(state: FleetState) -> MemberStep:
    """计算成员集合调整的下一步。

    Args:
        state: 本轮换船的可变编队事实。

    Returns:
        下一步决策：成员齐全、跳过、重新规划或选船。
    """
    protected, satisfied, target_positions = get_assignment_locations(
        state.current,
        state.occupied,
        state.assigned,
        state.verified_slots,
    )
    missing = [
        slot for slot in _get_target_order(state.assigned, state.selectors) if slot not in satisfied
    ]
    if not missing:
        return MemberStep(kind='done')

    target_slot = missing[0]
    option = state.assigned[target_slot]
    if option is None:
        return MemberStep(kind='skip', target_slot=target_slot)

    ship_slot = _get_replacement_slot(
        state.current,
        state.occupied,
        option,
        protected,
        target_positions.get(target_slot),
        state.attempted,
        target_slot,
    )
    if ship_slot is None:
        return MemberStep(kind='replan', target_slot=target_slot, option=option)
    return MemberStep(
        kind='select',
        target_slot=target_slot,
        ship_slot=ship_slot,
        option=option,
    )


def plan_deferred_fallback(
    state: FleetState,
    target_slot: int,
    selector: FleetSlotRule,
) -> ShipSelector | None:
    """在原物理槽位按规则顺序挑一个全局不冲突的备选先顶上。

    Args:
        state: 本轮换船的可变编队事实。
        target_slot: 需要释放的零基逻辑槽位。
        selector: 该槽位的原始规则。

    Returns:
        可作为过渡的备选规则；没有可用备选时为 None。
    """
    blocked = {
        identity
        for slot, name in enumerate(state.current)
        if slot != target_slot
        and state.occupied[slot]
        and (identity := get_ship_name_identity(name)) is not None
    }
    blocked.update(
        identity
        for slot, option in enumerate(state.assigned)
        if slot != target_slot
        and option is not None
        and (identity := get_ship_name_identity(option.name)) is not None
    )

    for candidate in selector.candidates:
        identity = get_ship_name_identity(candidate.name)
        if identity is None or identity in blocked or (target_slot, candidate) in state.unavailable:
            continue
        return candidate
    return None


# ── 目标分配辅助 ────────────────────────────────────────────────────────────


def _get_current_identities(current: Sequence[str | None]) -> set[str]:
    """收集当前编队里可识别的舰名身份。

    Args:
        current: 当前六槽舰名。

    Returns:
        当前编队中出现的舰名身份集合。
    """
    return {identity for name in current if (identity := get_ship_name_identity(name)) is not None}


def _build_slot_options(
    selectors: Sequence[FleetSlotRule | None],
    current_identities: set[str],
    unavailable: set[tuple[int, ShipSelector]] | frozenset[tuple[int, ShipSelector]],
    locked: dict[int, ShipSelector],
) -> list[tuple[ShipSelector | None, ...]] | None:
    """按槽位展开候选规则，队内已有的舰名排在前面。

    Args:
        selectors: 逐槽规则，None 表示该槽留空。
        current_identities: 当前编队中出现的舰名身份。
        unavailable: 已判定不可用的（零基槽位，规则）组合。
        locked: 已锁定不能改派的零基槽位与规则。

    Returns:
        逐槽候选规则；锁定项与规则冲突时为 None。
    """
    slot_options: list[tuple[ShipSelector | None, ...]] = []
    for slot, selector in enumerate(selectors):
        if selector is None:
            if slot in locked:
                return None
            slot_options.append((None,))
            continue

        locked_option = locked.get(slot)
        if locked_option is not None:
            if locked_option not in selector.options or (slot, locked_option) in unavailable:
                return None
            slot_options.append((locked_option,))
            continue

        if selector.primary is not None and (slot, selector.primary) not in unavailable:
            slot_options.append((selector.primary,))
            continue

        ranked = [
            (index, option)
            for index, option in enumerate(selector.candidates)
            if (slot, option) not in unavailable
        ]
        ranked.sort(
            key=lambda item: (
                get_ship_name_identity(item[1].name) not in current_identities,
                item[0],
            ),
        )
        slot_options.append(tuple(option for _, option in ranked))
    return slot_options


__all__ = [
    'FleetState',
    'MemberStep',
    'build_deferred_primary_slots',
    'build_snapshot_verified_slots',
    'build_target_pool',
    'get_assignment_locations',
    'get_target_names',
    'is_assignment_satisfied',
    'is_member_set_satisfied',
    'match_existing_members',
    'plan_deferred_fallback',
    'plan_member_step',
    'plan_target_options',
]
