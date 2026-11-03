"""模块功能：把 checker 的识别原文后处理成结构化舰队事实。

上层调用：
- fleet_select.operation.fleet_snapshot：把准备页六槽的舰名、舰种、等级原文合成快照。
- fleet_select.operation.ship_select：把船池列表一屏文字定位成候选船卡。

下层依赖：
- fleet_select.rules.shipnames：舰名纠错、模糊匹配与同船身份比较。
- fleet_select.rules.constants：国籍括号形态、等级形近字与匹配阈值。
- application.controller.types：舰种枚举。
- fleet_select.types：舰队快照数据契约。

边界：只做 OCR 后处理，不读图、不点击、不判断编队规则是否满足。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from autowsgr.application.controller.types import ShipType
from autowsgr.application.fleet_select.rules.constants import (
    CONTEXT_MATCH_THRESHOLD,
    COUNTRY_SUFFIX_PATTERN,
    LEVEL_DIGIT_TRANSLATION,
    LEVEL_MAX,
    LEVEL_MIN,
    SHIP_FUZZY_THRESHOLD,
)
from autowsgr.application.fleet_select.rules.shipnames import (
    SHIPNAMES,
    correct_ship_name,
    get_ship_name_identity,
    select_ship_name,
)
from autowsgr.application.fleet_select.types import FleetSnapshot


if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


# 舰种名到枚举值的反查表；枚举值是游戏里的中文舰种全称。
_SHIP_TYPE_BY_NAME = {member.value: member for member in ShipType}

# 舰种文字可能带国籍括号，例如「轻母(U国)」，匹配枚举前先剥掉。
_COUNTRY_SUFFIX_REGEX = re.compile(COUNTRY_SUFFIX_PATTERN)

# 等级文字的形态是「LV.110」；只认这个前缀，避免把星级或其它数字当成等级。
_LEVEL_REGEX = re.compile(r'[Ll][Vv]\.?\s*([0-9ILilOoDdSsBb]{1,6})')

# 船卡以舰名为中心，一张卡的文字都落在这个横向半宽内；实测同卡最远 0.009，
# 相邻卡中心相距 0.109，取 0.05 能分开并排的两张卡。
_CARD_HALF_WIDTH = 0.05

# 船卡纵向半高：实测卡内舰种到舰名相距 0.074，上下相邻两张卡相距 0.25，
# 取 0.10 只收本卡文字，不会串到上下相邻的卡上。
_CARD_HALF_HEIGHT = 0.10

_Parsed = TypeVar('_Parsed')


# ── 列表文字与船卡 ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ShipListRow:
    """船池列表里的一条文字与它在整帧里的位置。"""

    text: str
    center: tuple[float, float]
    region: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ShipCard:
    """船池列表里的一张船卡：命中的舰名文字与同行的舰种、等级。"""

    name: ShipListRow
    ship_type: ShipType | None = None
    level: int | None = None


# ── 文字解析 ────────────────────────────────────────────────────────────────


def _parse_ship_type(text: str | None) -> ShipType | None:
    """把舰种原文剥掉国籍括号后按枚举值反查。

    Args:
        text: 舰种识别原文，可能带国籍括号，也可能是噪声。

    Returns:
        枚举内的舰种；不在枚举内或为空时为 None。
    """
    if text is None:
        return None
    return _SHIP_TYPE_BY_NAME.get(_COUNTRY_SUFFIX_REGEX.sub('', text).strip())


def _parse_level(text: str | None) -> int | None:
    """把等级原文解析成等级数字。

    Args:
        text: 等级识别原文，形如「LV.110」或带形近字的误识别结果。

    Returns:
        合法区间内的等级；没有等级前缀或超出区间时为 None。
    """
    if text is None:
        return None
    match = _LEVEL_REGEX.search(text)
    if match is None:
        return None
    digits = ''.join(LEVEL_DIGIT_TRANSLATION.get(char, char) for char in match.group(1))
    if not digits.isdigit():
        return None
    level = int(digits)
    return level if LEVEL_MIN <= level <= LEVEL_MAX else None


# ── 准备页快照 ──────────────────────────────────────────────────────────────


def build_snapshot(
    *,
    occupied: Sequence[bool],
    name_texts: Sequence[str | None],
    ship_type_texts: Sequence[str | None] | None = None,
    ship_level_texts: Sequence[str | None] | None = None,
    expected_slot_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
) -> FleetSnapshot:
    """把一帧的原始识别结果合成六槽舰队快照。

    舰名按三档比对：先查完整舰名表，再用本槽目标舰名补救，最后用全局目标池
    补救。空槽不采信舰名，避免把空槽的占位文字当成舰船。

    Args:
        occupied: 六个槽位的血条占用结论。
        name_texts: 六个槽位的舰名识别原文。
        ship_type_texts: 六个槽位的舰种识别原文；不读细节时为 None。
        ship_level_texts: 六个槽位的等级识别原文；不读细节时为 None。
        expected_slot_names: 逐槽目标舰名，用作第二档补救匹配。
        expected_pool: 全部目标舰名，用作第三档补救匹配。

    Returns:
        合并后的舰队快照。
    """
    pool = list(expected_pool or ())
    names = tuple(
        _get_matched_ship_name(text, _get_expected_name(expected_slot_names, slot), pool)
        if is_occupied
        else None
        for slot, (text, is_occupied) in enumerate(zip(name_texts, occupied, strict=True))
    )
    ship_types = (
        tuple(_parse_ship_type(text) for text in ship_type_texts)
        if ship_type_texts is not None
        else None
    )
    ship_levels = (
        tuple(_parse_level(text) for text in ship_level_texts)
        if ship_level_texts is not None
        else None
    )
    return FleetSnapshot(
        names=names,
        occupied=tuple(occupied),
        ship_types=ship_types,
        ship_levels=ship_levels,
    )


# ── 船池卡片 ────────────────────────────────────────────────────────────────


def recognize_ship_cards(texts: Sequence[ShipListRow], name: str) -> list[ShipCard]:
    """在一屏列表文字里找出所有属于目标舰名的船卡。

    每一处命中目标舰名的文字就是一张卡的中心，该中心附近一小块区域内的其余
    文字是这张卡的舰种与等级。船池是网格布局，同一行能并排多张同名卡，所以
    按舰名就近归组，不能按整行归组。

    Args:
        texts: 船池列表一帧里的全部文字与位置。
        name: 目标舰名，来自选船规则。

    Returns:
        按识别顺序排列的船卡；同屏没有这艘船时为空。
    """
    cards: list[ShipCard] = []
    for anchor in (item for item in texts if _is_same_ship(name, item.text)):
        members = [
            item
            for item in texts
            if abs(item.center[0] - anchor.center[0]) <= _CARD_HALF_WIDTH
            and abs(item.center[1] - anchor.center[1]) < _CARD_HALF_HEIGHT
        ]
        cards.append(
            ShipCard(
                name=anchor,
                ship_type=_get_single_value(_parse_ship_type(item.text) for item in members),
                level=_get_single_value(_parse_level(item.text) for item in members),
            )
        )
    return cards


# ── 舰名比对 ────────────────────────────────────────────────────────────────


def _get_expected_name(expected_slot_names: Sequence[str | None] | None, slot: int) -> str | None:
    """取某一槽位的目标舰名，未提供时返回 None。

    Args:
        expected_slot_names: 逐槽目标舰名；None 表示调用方没有可用的上下文。
        slot: 槽位下标，0 基。

    Returns:
        该槽位的目标舰名；越界或未提供时为 None。
    """
    if expected_slot_names is None or slot >= len(expected_slot_names):
        return None
    return expected_slot_names[slot]


def _get_matched_ship_name(
    text: str | None,
    expected_name: str | None,
    pool: list[str],
) -> str | None:
    """把 OCR 原文按三档比对成标准舰名。

    Args:
        text: 舰名识别原文。
        expected_name: 本槽位的目标舰名，用作第二档补救匹配。
        pool: 全部目标舰名，用作第三档补救匹配。

    Returns:
        比对上的标准舰名；三档都没命中时为 None。
    """
    if text is None:
        return None

    corrected = correct_ship_name(text)
    matched = select_ship_name(corrected, SHIPNAMES, threshold=SHIP_FUZZY_THRESHOLD)
    if matched is not None:
        return matched
    if expected_name is not None:
        matched = select_ship_name(
            corrected,
            [expected_name],
            threshold=CONTEXT_MATCH_THRESHOLD,
        )
        if matched is not None:
            return matched
    if pool:
        return select_ship_name(corrected, pool, threshold=CONTEXT_MATCH_THRESHOLD)
    return None


def _get_single_value(values: Iterable[_Parsed | None]) -> _Parsed | None:
    """取一组解析结果里唯一的非空值；没有或互相冲突时为 None。

    Args:
        values: 同一张船卡上各条文字解析出的值。

    Returns:
        唯一的非空值；全为空或存在冲突时为 None。
    """
    distinct = {value for value in values if value is not None}
    return next(iter(distinct)) if len(distinct) == 1 else None


def _is_same_ship(target: str, text: str) -> bool:
    """比较目标舰名与列表上的原文，不修改任何一方。

    Args:
        target: 选船规则里的目标舰名。
        text: 列表上的原文。

    Returns:
        两者归一化后的身份一致时为 True。
    """
    identity = get_ship_name_identity(target)
    return identity is not None and identity == get_ship_name_identity(text)


__all__ = [
    'ShipCard',
    'ShipListRow',
    'build_snapshot',
    'recognize_ship_cards',
]
