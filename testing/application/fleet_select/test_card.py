"""模块功能：验证船池列表的卡片归行、舰种等级解析与约束判定。

直接调用方：项目测试运行器。

直接依赖：fleet_select.rules.ocr、fleet_select.rules.constraints 与选船规则数据。

边界：列表文字用替身构造，不截图、不读模板、不点设备。
"""

from __future__ import annotations

import pytest

from autowsgr.application.controller.types import ShipType
from autowsgr.application.fleet_select.rules.constraints import CardVerdict, get_card_verdict
from autowsgr.application.fleet_select.rules.ocr import (
    ShipCard,
    ShipListRow,
    _parse_level,
    _parse_ship_type,
    recognize_ship_cards,
)
from autowsgr.application.fleet_select.types import ShipSelector


def _text(text: str, *, x: float, y: float) -> ShipListRow:
    """构造一段列表文字；区域只用于表达位置，取中心附近的小框。"""
    return ShipListRow(
        text=text,
        center=(x, y),
        region=(x - 0.04, y - 0.01, x + 0.04, y + 0.01),
    )


def _row(
    *, name: str, ship_type: str, level: str, y: float, x: float = 0.30
) -> tuple[ShipListRow, ...]:
    """构造一张船卡的三行文字：舰种与等级在上、舰名在下，横向围绕舰名居中。"""
    return (
        _text(ship_type, x=x - 0.01, y=y - 0.070),
        _text(name, x=x, y=y),
        _text(level, x=x + 0.02, y=y - 0.045),
    )


def _card(ship_type: ShipType | None, level: int | None) -> ShipCard:
    """构造一张只关心舰种与等级的船卡。"""
    return ShipCard(
        name=_text('企业', x=0.30, y=0.30),
        ship_type=ship_type,
        level=level,
    )


# ── 文字解析 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('航母', ShipType.CV),
        ('轻母(U国)', ShipType.CVL),
        ('轻母（U国）', ShipType.CVL),
        ('战列 (J国)', ShipType.BB),
        ('航亩', None),
        ('', None),
    ],
)
def test_parse_ship_type(text: str, expected: ShipType | None) -> None:
    """舰种原文剥掉国籍括号后按枚举值反查。"""
    assert _parse_ship_type(text) is expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('LV.110', 110),
        ('lv. 100', 100),
        ('LV.SO', 50),
        ('LV.I10', 110),
        ('LV. 1', 1),
        ('LV. 0', None),
        ('LV. 111', None),
        ('110', None),
        ('', None),
    ],
)
def test_parse_level(text: str, expected: int | None) -> None:
    """等级原文按形近字归一后落在合法区间才算数。"""
    assert _parse_level(text) == expected


# ── 卡片归行 ────────────────────────────────────────────────────────────────


def test_find_cards_groups_one_row_into_one_card() -> None:
    """同一张卡的三段文字归到一张卡上。"""
    texts = _row(name='企业', ship_type='航母', level='LV.110', y=0.30)

    cards = recognize_ship_cards(texts, '企业')

    assert len(cards) == 1
    assert cards[0].ship_type is ShipType.CV
    assert cards[0].level == 110


def test_find_cards_keeps_adjacent_rows_apart() -> None:
    """上下两张卡的舰种与等级不会串到对方身上。"""
    texts = (
        *_row(name='企业', ship_type='航母', level='LV.110', y=0.30),
        *_row(name='俾斯麦', ship_type='战列', level='LV.90', y=0.55),
    )

    cards = recognize_ship_cards(texts, '企业')

    assert len(cards) == 1
    assert cards[0].ship_type is ShipType.CV
    assert cards[0].level == 110


def test_find_cards_separates_side_by_side_cards() -> None:
    """同一行并排两张同名卡各自成卡，等级不会混成未识别。"""
    texts = (
        *_row(name='企业', ship_type='航母', level='LV.110', y=0.30, x=0.20),
        *_row(name='企业', ship_type='航母', level='LV.10', y=0.30, x=0.31),
    )

    cards = recognize_ship_cards(texts, '企业')

    assert [card.level for card in cards] == [110, 10]
    assert [card.ship_type for card in cards] == [ShipType.CV, ShipType.CV]


def test_find_cards_returns_empty_when_ship_absent() -> None:
    """列表里没有这艘船时不返回任何卡片。"""
    texts = _row(name='俾斯麦', ship_type='战列', level='LV.90', y=0.30)

    assert recognize_ship_cards(texts, '企业') == []


def test_find_cards_drops_conflicting_ship_type() -> None:
    """同一行读出互相冲突的舰种时按未识别处理。"""
    texts = (
        _text('航母', x=0.18, y=0.290),
        _text('轻母', x=0.22, y=0.292),
        _text('企业', x=0.30, y=0.300),
    )

    cards = recognize_ship_cards(texts, '企业')

    assert len(cards) == 1
    assert cards[0].ship_type is None


# ── 约束判定 ────────────────────────────────────────────────────────────────


def test_judge_card_accepts_matching_constraints() -> None:
    """舰种与等级都满足时直接接受。"""
    selector = ShipSelector(name='企业', ship_types=(ShipType.CV,), min_level=100)

    verdict = get_card_verdict(selector, _card(ShipType.CV, 110))

    assert verdict.accepted
    assert not verdict.is_fallback


def test_judge_card_rejects_mismatched_ship_type() -> None:
    """舰种不在规则集合里时淘汰。"""
    selector = ShipSelector(name='企业', ship_types=(ShipType.CV,))

    assert not get_card_verdict(selector, _card(ShipType.BB, None)).accepted


def test_judge_card_rejects_unknown_ship_type_when_strict() -> None:
    """严格规则下舰种读不出来就淘汰。"""
    selector = ShipSelector(name='企业', ship_types=(ShipType.CV,))

    assert not get_card_verdict(selector, _card(None, None)).accepted


def test_judge_card_marks_unknown_ship_type_as_fallback_when_relaxed() -> None:
    """放宽规则下舰种读不出来只记未知，仍可作为后备候选。"""
    selector = ShipSelector(
        name='企业',
        ship_types=(ShipType.CV,),
        relaxed_constraints=True,
    )

    verdict = get_card_verdict(selector, _card(None, None))

    assert verdict.accepted
    assert verdict.type_unknown
    assert verdict.fallback_priority == (1, True)


def test_judge_card_rejects_level_out_of_range() -> None:
    """等级超出规则区间时淘汰。"""
    selector = ShipSelector(name='企业', min_level=100, max_level=110)

    assert not get_card_verdict(selector, _card(None, 90)).accepted


def test_judge_card_rejects_unknown_level_when_strict() -> None:
    """严格规则下等级读不出来就淘汰。"""
    selector = ShipSelector(name='企业', max_level=110)

    assert not get_card_verdict(selector, _card(None, None)).accepted


def test_judge_card_marks_unknown_level_as_fallback_when_relaxed() -> None:
    """放宽规则下等级读不出来只记未知，仍可作为后备候选。"""
    selector = ShipSelector(name='企业', max_level=110, relaxed_constraints=True)

    verdict = get_card_verdict(selector, _card(None, None))

    assert verdict.accepted
    assert verdict.level_unknown
    assert verdict.fallback_priority == (1, False)


def test_judge_card_accepts_relaxed_card_with_readable_level() -> None:
    """放宽规则但字段都读得出来时，这张卡不算后备候选。"""
    selector = ShipSelector(name='企业', max_level=110, relaxed_constraints=True)

    assert not get_card_verdict(selector, _card(None, 90)).is_fallback


def test_card_verdict_orders_fallback_by_unknown_field_count() -> None:
    """未知字段越少的后备候选越优先，舰种未知比等级未知更靠后。"""
    assert CardVerdict(accepted=True).fallback_priority == (0, False)
    assert CardVerdict(accepted=True, level_unknown=True).fallback_priority == (1, False)
    assert CardVerdict(accepted=True, type_unknown=True).fallback_priority == (1, True)
    assert CardVerdict(accepted=True, level_unknown=True, type_unknown=True).fallback_priority == (
        2,
        True,
    )
