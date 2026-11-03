"""模块功能：验证严格与宽泛两种匹配失败时不会误选舰船。

直接调用方：项目测试运行器。

直接依赖：fleet_select.operation.ship_select 与船卡识别、约束判定。

边界：船池页、槽位页与列表文字全部换成替身，不截图、不点真机；判定链本身
（recognize_ship_cards 与 get_card_verdict）保持真实，只伪装页面事实。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from autowsgr.application.fleet_select.operation import ship_select as ship_select_module
from autowsgr.application.fleet_select.operation.ship_select import select_ship
from autowsgr.application.fleet_select.rules.ocr import ShipListRow
from autowsgr.application.fleet_select.types import ShipSelector


if TYPE_CHECKING:
    import pytest


def _row(text: str, *, x: float, y: float) -> ShipListRow:
    """构造一段列表文字；区域只用于表达位置，取中心附近的小框。"""
    return ShipListRow(
        text=text,
        center=(x, y),
        region=(x - 0.04, y - 0.01, x + 0.04, y + 0.01),
    )


def _enterprise_rows(*, level: str) -> tuple[ShipListRow, ...]:
    """构造一张企业号的船卡：舰种与等级在上，舰名在下。"""
    return (
        _row('航母', x=0.29, y=0.230),
        _row('LV.' + level, x=0.32, y=0.255),
        _row('企业', x=0.30, y=0.300),
    )


_CLICKED: list[tuple[float, float]] = []


class _FakePoolPage:
    """记录点卡落点、其余页面动作一律成功的船池页替身。"""

    def __init__(self, _ctx: Any) -> None:
        """保持与真实页面一致的构造签名。"""

    def click_search_box(self) -> None:
        """搜索框点击不产生副作用。"""

    def input_ship_name(self, _name: str) -> None:
        """搜索词输入不产生副作用。"""

    def confirm_search(self) -> None:
        """提交搜索不产生副作用。"""

    def scroll_list_down(self) -> None:
        """搜索后只扫一屏，不应当滚动。"""
        raise AssertionError('搜索生效后不应继续滚动列表')

    def click_card_at(self, center: tuple[float, float]) -> None:
        """记录点卡落点。"""
        _CLICKED.append(center)

    def go_back(self) -> None:
        """返回准备页不产生副作用。"""


def _patch_pool(monkeypatch: pytest.MonkeyPatch, rows: tuple[ShipListRow, ...]) -> None:
    """把船池页与槽位页换成替身，并固定一屏列表文字。"""
    _CLICKED.clear()
    monkeypatch.setattr(ship_select_module, 'ShipPoolPage', _FakePoolPage)
    monkeypatch.setattr(
        ship_select_module,
        'FleetSlotPage',
        lambda _ctx: SimpleNamespace(click_slot=lambda _slot: None),
    )
    monkeypatch.setattr(ship_select_module, 'check_ship_pool_page', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ship_select_module, 'check_search_input', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ship_select_module, 'read_ship_list_texts', lambda _ctx: list(rows))


def test_select_ship_accepts_card_matching_strict_level(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """对照组：等级确实满足严格约束时正常选中，证明替身链路本身可用。"""
    _patch_pool(monkeypatch, _enterprise_rows(level='110'))

    selected = select_ship(ctx, slot=1, selectors=[ShipSelector(name='企业', min_level=100)])

    assert selected == '企业'
    assert len(_CLICKED) == 1


def test_select_ship_rejects_card_failing_strict_level(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """严格匹配失败：船只读到等级 10，低于最低等级要求，不能点卡。"""
    _patch_pool(monkeypatch, _enterprise_rows(level='10'))

    selected = select_ship(ctx, slot=1, selectors=[ShipSelector(name='企业', min_level=100)])

    assert selected is None
    assert _CLICKED == []


def test_select_ship_rejects_card_failing_relaxed_level(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """宽泛匹配失败：等级读得出来时不放宽，10 级仍不满足最低等级要求。"""
    _patch_pool(monkeypatch, _enterprise_rows(level='10'))

    selected = select_ship(
        ctx,
        slot=1,
        selectors=[ShipSelector(name='企业', min_level=100, relaxed_constraints=True)],
    )

    assert selected is None
    assert _CLICKED == []


def test_select_ship_accepts_card_when_relaxed_level_is_unreadable(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """宽泛匹配成功：等级读不出来时只记未知，仍可作为后备候选选中。"""
    rows = (
        _row('航母', x=0.29, y=0.230),
        _row('企业', x=0.30, y=0.300),
    )
    _patch_pool(monkeypatch, rows)

    selected = select_ship(
        ctx,
        slot=1,
        selectors=[ShipSelector(name='企业', min_level=100, relaxed_constraints=True)],
    )

    assert selected == '企业'
