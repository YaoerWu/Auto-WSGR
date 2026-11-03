"""模块功能：判断舰名、舰种和等级是否满足规范化舰队选择规则。

上层调用：
- fleet_select.rules.planner：生成可行目标、校验槽位分配。
- fleet_select.operation.ship_select：判断船池里的一张船卡能不能点。

下层依赖：
- fleet_select.types：舰队快照与槽位规则的数据形态。
- fleet_select.rules.shipnames：舰名归一化与同船身份比较。
- fleet_select.rules.ocr：船卡上的舰种与等级。

边界：只判断规则是否满足，不分配目标、不操作页面、不写舰队状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.fleet_select.rules.shipnames import (
    get_ship_name_identity,
    normalize_ship_name,
)
from autowsgr.application.fleet_select.types import (
    FLEET_SLOT_COUNT,
    FleetSlotRule,
    ShipSelector,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.fleet_select.rules.ocr import ShipCard
    from autowsgr.application.fleet_select.types import FleetSnapshot, ShipType


# ── 船卡判定结果 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CardVerdict:
    """一条选船规则对一张船卡的约束判断结果。"""

    accepted: bool
    type_unknown: bool = False
    level_unknown: bool = False

    @property
    def is_fallback(self) -> bool:
        """判断该船卡是否只能作为放宽规则的后备候选。"""
        return self.type_unknown or self.level_unknown

    @property
    def fallback_priority(self) -> tuple[int, bool]:
        """返回后备候选排序键，优先选择未知字段更少的船卡。"""
        return (
            int(self.type_unknown) + int(self.level_unknown),
            self.type_unknown,
        )


# ── 规则归一化 ──────────────────────────────────────────────────────────────


def normalize_rules(
    rules: Sequence[FleetSlotRule | str | None],
) -> list[FleetSlotRule | None]:
    """把舰名或槽位规则统一成六槽规则，不足六槽的按空槽补齐。

    Args:
        rules: 逐槽规则，可以直接写舰名。

    Returns:
        长度固定为六个槽位的规则列表。

    Raises:
        ValueError: 规则数量超过六个槽位。
        TypeError: 出现不支持的槽位规则类型。
    """
    if len(rules) > FLEET_SLOT_COUNT:
        raise ValueError(f'编队规则最多 {FLEET_SLOT_COUNT} 个槽位，实际为 {len(rules)}')

    selectors: list[FleetSlotRule | None] = []
    for value in rules:
        if isinstance(value, str):
            selectors.append(FleetSlotRule(primary=ShipSelector(name=value)))
        elif value is None or isinstance(value, FleetSlotRule):
            selectors.append(value)
        else:
            raise TypeError(f'编队槽位规则类型不支持: {value!r}')
    return [*selectors, *([None] * (FLEET_SLOT_COUNT - len(selectors)))]


# ── 单条规则 ────────────────────────────────────────────────────────────────


def is_option_name_matched(current_name: str | None, option: ShipSelector) -> bool:
    """判断准备页舰名是否与一条精确规则属于同一舰船身份。

    Args:
        current_name: 准备页读到的标准舰名，未识别为 None。
        option: 待比对的选船规则。

    Returns:
        舰名身份一致且满足搜索名约束时为 True。
    """
    return get_ship_name_identity(current_name) == get_ship_name_identity(
        option.name,
    ) and is_search_name_matched(current_name, option.search_name)


def is_search_name_matched(current_name: str | None, raw_search_name: str | None) -> bool:
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

    return get_ship_name_identity(current_name) == get_ship_name_identity(search_name)


def get_option_for_name(
    name: str | None,
    fleet_slot_rule: FleetSlotRule | None,
) -> ShipSelector | None:
    """返回与实际舰名对应的那条独立规则。

    Args:
        name: 准备页读到的标准舰名。
        fleet_slot_rule: 该槽位的规则集合，可为空。

    Returns:
        身份一致的规则；找不到时为 None。
    """
    identity = get_ship_name_identity(name)
    candidates = list(fleet_slot_rule.options) if fleet_slot_rule is not None else []
    if not candidates:
        normalized = normalize_ship_name(name)
        return ShipSelector(name=normalized) if normalized else None
    return next(
        (option for option in candidates if get_ship_name_identity(option.name) == identity),
        None,
    )


def should_validate_selection(option: ShipSelector | None) -> bool:
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


def is_snapshot_satisfied_option(
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


# ── 船池卡片 ────────────────────────────────────────────────────────────────


def get_card_verdict(option: ShipSelector, card: ShipCard) -> CardVerdict:
    """按舰种、等级顺序判断一张船卡是否满足选船规则。

    放宽约束的规则把识别不到的字段记成未知而不是直接淘汰；没有写舰种或等级
    约束的字段不参与判断。

    Args:
        option: 待比对的选船配置。
        card: 列表上认领到的船卡。

    Returns:
        是否接受这张卡，以及哪些字段是放宽后才接受的未知值。
    """
    type_unknown = False
    if option.ship_types:
        if card.ship_type is None:
            if not option.relaxed_constraints:
                return CardVerdict(accepted=False)
            type_unknown = True
        elif card.ship_type not in option.ship_types:
            return CardVerdict(accepted=False)

    level_unknown = False
    if option.min_level is not None or option.max_level is not None:
        if card.level is None:
            if not option.relaxed_constraints:
                return CardVerdict(accepted=False)
            level_unknown = True
        elif not _is_level_in_range(card.level, option.min_level, option.max_level):
            return CardVerdict(accepted=False)

    return CardVerdict(accepted=True, type_unknown=type_unknown, level_unknown=level_unknown)


# ── 整队规则 ────────────────────────────────────────────────────────────────


def is_campaign_types_matched(
    snapshot: FleetSnapshot,
    required_types: Sequence[ShipType],
    *,
    validate_types: bool = True,
) -> bool:
    """校验战役编成：前几槽正好是要的舰种，其后没有多余舰船。

    Args:
        snapshot: 当前舰队快照。
        required_types: 从一号位开始逐槽要求的舰种。
        validate_types: 是否比对舰种，关闭后只要求这些槽位有船。

    Returns:
        前几槽符合要求且其后没有多余舰船时为 True。

    Raises:
        ValueError: 要求的舰种数量不在一个到六个之间。
    """
    if not 1 <= len(required_types) <= FLEET_SLOT_COUNT:
        raise ValueError(f'战役舰种规则必须包含 1-{FLEET_SLOT_COUNT} 个槽位')

    ship_types = snapshot.ship_types or ()
    if not all(
        snapshot.occupied[slot] and (not validate_types or ship_types[slot] is expected)
        for slot, expected in enumerate(required_types)
    ):
        return False
    return not any(snapshot.occupied[len(required_types) :])


def _is_level_in_range(level: int, min_level: int | None, max_level: int | None) -> bool:
    """判断识别等级是否落在规则指定的范围内。

    Args:
        level: 船卡上识别到的等级。
        min_level: 允许的最低等级；None 表示不设下限。
        max_level: 允许的最高等级；None 表示不设上限。

    Returns:
        等级在闭区间内时为 True。
    """
    if min_level is not None and level < min_level:
        return False
    return max_level is None or level <= max_level


__all__ = [
    'CardVerdict',
    'get_card_verdict',
    'get_option_for_name',
    'is_campaign_types_matched',
    'is_option_name_matched',
    'is_search_name_matched',
    'is_snapshot_satisfied_option',
    'normalize_rules',
    'should_validate_selection',
]
