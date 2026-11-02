"""模块功能：判断舰名、舰种和等级是否满足规范化舰队选择规则。

上层调用：
- fleet_select.planning：生成可行目标和槽位分配。
- fleet_select.alignment：验证编队调整结果。

下层依赖：
- fleet_select.models：舰队快照与槽位规则的数据形态。
- fleet_select.names：舰名归一化与同船身份比较。

本模块只判断规则，不分配目标、不操作页面、不写舰队状态。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.fleet_select.models import (
    FLEET_SLOT_COUNT,
    ShipSelector,
)
from autowsgr.application.fleet_select.names import normalize_ship_name, ship_name_identity


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.fleet_select.models import (
        FleetSlotRule,
        FleetSnapshot,
    )


# ── 单条规则 ────────────────────────────────────────────────────────────────


def option_matches_name(current_name: str | None, option: ShipSelector) -> bool:
    """判断准备页舰名是否与一条精确规则属于同一舰船身份。

    Args:
        current_name: 准备页读到的标准舰名，未识别为 None。
        option: 待比对的选船规则。

    Returns:
        舰名身份一致且满足搜索名约束时为 True。
    """
    return ship_name_identity(current_name) == ship_name_identity(
        option.name,
    ) and matches_search_name(current_name, option.search_name)


def matches_search_name(current_name: str | None, raw_search_name: str | None) -> bool:
    """判断当前标准舰名是否符合规则指定的搜索名。

    Args:
        current_name: 准备页读到的标准舰名。
        raw_search_name: 规则里的搜索名；为空表示不限制。

    Returns:
        搜索名为空、文本相等或身份相等时为 True。
    """
    if current_name is None:
        return False
    if raw_search_name is None:
        return True

    search_name = raw_search_name.strip()
    if not search_name:
        return True
    if current_name == search_name:
        return True

    return ship_name_identity(current_name) == ship_name_identity(search_name)


def option_for_name(name: str | None, selector: FleetSlotRule | None) -> ShipSelector | None:
    """返回与实际舰名对应的那条独立规则。

    Args:
        name: 准备页读到的标准舰名。
        selector: 该槽位的规则集合，可为空。

    Returns:
        身份一致的规则；找不到时为 None。
    """
    identity = ship_name_identity(name)
    return next(
        (
            option
            for option in _slot_options(name, selector)
            if ship_name_identity(option.name) == identity
        ),
        None,
    )


def requires_selection_validation(option: ShipSelector | None) -> bool:
    """返回规则是否必须通过船池页面复核舰种或等级。

    Args:
        option: 待判断的选船规则。

    Returns:
        规则带舰种或等级约束且未放宽时为 True。
    """
    return bool(
        option is not None
        and not option.relaxed_constraints
        and (option.ship_types or option.min_level is not None or option.max_level is not None)
    )


def snapshot_satisfies_option(
    snapshot: FleetSnapshot,
    slot: int,
    option: ShipSelector,
) -> bool:
    """强校验：判断快照某槽位的舰种与等级是否满足规则。

    名称匹配由调用方保证，这里只校验约束。放宽约束的规则不走本函数。

    Args:
        snapshot: 当前舰队快照。
        slot: 零基槽位下标。
        option: 待比对的选船规则。

    Returns:
        舰种与等级都满足约束时为 True。
    """
    ship_type = snapshot.ship_types[slot] if snapshot.ship_types else None
    ship_level = snapshot.ship_levels[slot] if snapshot.ship_levels else None

    if option.ship_types and ship_type not in option.ship_types:
        return False
    if option.min_level is not None or option.max_level is not None:
        if ship_level is None:
            return False
        if option.min_level is not None and ship_level < option.min_level:
            return False
        if option.max_level is not None and ship_level > option.max_level:
            return False
    return True


# ── 整队规则 ────────────────────────────────────────────────────────────────


def validate_fleet(
    current: Sequence[str | None],
    desired: Sequence[str | None],
    selectors: Sequence[FleetSlotRule | None],
    verified_slots: set[int] | frozenset[int] = frozenset(),
) -> bool:
    """验证六个槽位是否完整满足目标，并拒绝队内同名舰。

    Args:
        current: 当前六槽舰名。
        desired: 目标六槽舰名。
        selectors: 逐槽规则，可为空。
        verified_slots: 已通过船池页面复核约束的零基槽位集合。

    Returns:
        成员无重复且逐槽匹配目标时为 True。
    """
    members = [ship_name_identity(name) for name in current if name is not None]
    if len(members) != len(set(members)):
        return False

    return all(
        _slot_matches(
            current[slot],
            desired[slot],
            selectors[slot],
            selection_verified=slot in verified_slots,
        )
        for slot in range(FLEET_SLOT_COUNT)
    )


# ── 私有实现 ────────────────────────────────────────────────────────────────


def _slot_options(name: str | None, selector: FleetSlotRule | None) -> list[ShipSelector]:
    """按已分配舰名优先、其余规则随后的顺序生成本槽完整规则。"""
    normalized_name = normalize_ship_name(name)
    if selector is None:
        return [ShipSelector(name=normalized_name)] if normalized_name else []

    options = list(selector.options)
    target_identity = ship_name_identity(normalized_name)
    options.sort(key=lambda option: ship_name_identity(option.name) != target_identity)
    return options


def _slot_matches(
    current_name: str | None,
    target: str | None,
    selector: FleetSlotRule | None,
    *,
    selection_verified: bool = False,
) -> bool:
    """判断一个当前槽位是否满足对应的目标舰名和搜索规则。"""
    if target is None:
        return current_name is None
    if selector is None:
        return ship_name_identity(current_name) == ship_name_identity(target)
    option = option_for_name(current_name, selector)
    if option is None:
        return False
    if requires_selection_validation(option) and not selection_verified:
        return False
    return matches_search_name(current_name, option.search_name)


__all__ = [
    'matches_search_name',
    'option_for_name',
    'option_matches_name',
    'requires_selection_validation',
    'snapshot_satisfies_option',
    'validate_fleet',
]
