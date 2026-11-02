"""模块功能：根据舰队规则和当前快照计算唯一目标及槽位规划。

上层调用：
- fleet_select.alignment：获取目标分配、槽位定位和处理顺序。
- fleet_select.battle_preparation.normal：生成目标并验证最终编队。

下层依赖：
- fleet_select.rules：判断规则与舰船身份。
- fleet_select.names：舰名归一化与身份比较。

本模块只计算目标，不执行页面操作、不读图、不写舰队状态。

目标分配规则：按 YAML 主选优先、备选靠后的顺序做全局唯一分配，
同一身份不得占用两个槽位，优先复用队内已有舰船。
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from autowsgr.application.fleet_select import rules
from autowsgr.application.fleet_select.models import FLEET_SLOT_COUNT
from autowsgr.application.fleet_select.names import normalize_ship_name, ship_name_identity
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.fleet_select.models import (
        FleetSlotRule,
        FleetSnapshot,
        ShipSelector,
    )


_log = get_logger('fleet_select.planning')


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
    current_identities = {
        identity for name in current if (identity := ship_name_identity(name)) is not None
    }
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
                ship_name_identity(item[1].name) not in current_identities,
                item[0],
            ),
        )
        slot_options.append(tuple(option for _, option in ranked))

    @cache
    def assign(
        slot: int,
        used: tuple[str, ...],
    ) -> tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None:
        if slot >= len(slot_options):
            return 0, (), ()

        best: tuple[int, tuple[int, ...], tuple[ShipSelector | None, ...]] | None = None
        used_set = set(used)
        for rank, option in enumerate(slot_options[slot]):
            if option is None:
                result = assign(slot + 1, used)
                identity = None
            else:
                identity = ship_name_identity(option.name)
                if identity is None or identity in used_set:
                    continue
                result = assign(slot + 1, tuple(sorted((*used, identity))))
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

    result = assign(0, ())
    return list(result[2]) if result is not None else None


def ocr_target_pool(selectors: Sequence[FleetSlotRule | None]) -> list[str]:
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
            identity = ship_name_identity(normalized)
            if normalized is not None and identity is not None and identity not in seen:
                pool.append(normalized)
                seen.add(identity)
    return pool


def target_names(assigned: Sequence[ShipSelector | None]) -> list[str | None]:
    """把精确规则转换为最终逐槽使用的标准舰名。

    Args:
        assigned: 逐槽精确规则。

    Returns:
        与槽位对齐的标准舰名，空槽为 None。
    """
    return [normalize_ship_name(option.name) if option is not None else None for option in assigned]


# ── 分配结果校验 ────────────────────────────────────────────────────────────


def validate_assignment(
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
        identity for name in current if (identity := ship_name_identity(name)) is not None
    ]
    if len(identities) != len(set(identities)):
        return False

    for slot, option in enumerate(assigned):
        if option is None:
            if occupied[slot] or current[slot] is not None:
                return False
            continue
        if not occupied[slot] or not rules.option_matches_name(current[slot], option):
            return False
        if rules.requires_selection_validation(option) and slot not in verified_slots:
            return False
    return True


def member_set_satisfied(
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
    protected, satisfied, _ = assignment_locations(
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


def mark_snapshot_verified_slots(
    snapshot: FleetSnapshot,
    assigned: Sequence[ShipSelector | None],
    verified_slots: set[int],
) -> None:
    """用首次快照标记已就位且满足规则的逻辑槽位，跳过选船二次确认。

    已确认无需更换的舰船不再进入点对点选船页更换，避免已就位舰船
    不在船池中导致选不到、重选、再选不到的循环。

    强校验：名称匹配后舰种与等级必须全部符合规则才标记，任一约束因
    OCR 缺失无法确认时也不标记，落入选船页权威校验。
    放宽约束的规则本就不要求选船校验，由赋值匹配直接放行。

    Args:
        snapshot: 首次截图得到的舰队快照。
        assigned: 逐槽精确规则。
        verified_slots: 就地写入的已确认零基槽位集合。
    """
    if snapshot.ship_types is None or snapshot.ship_levels is None:
        return
    for target_slot, option in enumerate(assigned):
        if option is None or not rules.requires_selection_validation(option):
            continue
        if target_slot in verified_slots:
            continue
        position = next(
            (
                slot
                for slot in range(FLEET_SLOT_COUNT)
                if snapshot.occupied[slot]
                and rules.option_matches_name(snapshot.names[slot], option)
            ),
            None,
        )
        if position is None:
            continue
        if not rules.snapshot_satisfies_option(snapshot, position, option):
            _log.debug(
                '[Fleet] 快照校验未通过: 逻辑槽位 {} ({}), 进入选船二次确认',
                target_slot + 1,
                snapshot.names[position],
            )
            continue
        verified_slots.add(target_slot)
        _log.debug(
            '[Fleet] 快照确认逻辑槽位 {} 已就位 ({}), 跳过选船二次确认',
            target_slot + 1,
            snapshot.names[position],
        )


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

    def matches(slot: int, ship: str | None) -> bool:
        selector = selectors[slot]
        option = rules.option_for_name(desired[slot], selector)
        return (
            ship_name_identity(ship) == ship_name_identity(desired[slot])
            and (option is None or rules.matches_search_name(ship, option.search_name))
            and (not rules.requires_selection_validation(option) or slot in verified_slots)
        )

    for slot in target_slots:
        if matches(slot, current[slot]):
            ok[slot] = True
            matched_slots.add(slot)
            used_positions.add(slot)

    for slot in target_slots:
        if slot in matched_slots:
            continue
        for position, ship in enumerate(current):
            if position in used_positions:
                continue
            if matches(slot, ship):
                ok[position] = True
                matched_slots.add(slot)
                used_positions.add(position)
                break

    return ok, matched_slots


def assignment_locations(
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
                and rules.option_matches_name(current[slot], option)
            ),
            None,
        )
        if position is None:
            continue
        protected.add(position)
        target_positions[target_slot] = position
        if not rules.requires_selection_validation(option) or target_slot in verified_slots:
            satisfied.add(target_slot)

    return protected, satisfied, target_positions


def target_order(
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


def replacement_slot(
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


__all__ = [
    'assignment_locations',
    'mark_snapshot_verified_slots',
    'match_existing_members',
    'member_set_satisfied',
    'ocr_target_pool',
    'plan_target_options',
    'replacement_slot',
    'target_names',
    'target_order',
    'validate_assignment',
]
