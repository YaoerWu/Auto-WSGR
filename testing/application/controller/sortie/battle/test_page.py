"""模块功能：验证征战页章节槽位与地图翻页的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.battle.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie.battle import page as battle_page_module
from autowsgr.application.controller.sortie.battle.page import BattlePage


if TYPE_CHECKING:
    from typing import Any


_SLOT_POSITIONS = tuple((0.1 * (index + 1), 0.2) for index in range(5))


def _stub_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    """用可断言的落点替身接管征战页常量。"""
    monkeypatch.setattr(
        battle_page_module,
        'constants',
        SimpleNamespace(
            CHAPTER_SLOT_POSITIONS=_SLOT_POSITIONS,
            CLICK_MAP_NEXT=(0.31, 0.32),
            CLICK_MAP_PREV=(0.41, 0.42),
            CLICK_ENTER_SORTIE=(0.51, 0.52),
        ),
    )


def test_click_chapter_slot_clicks_each_visible_slot(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """五个可见章节槽位按索引各自点击。"""
    _stub_constants(monkeypatch)

    page = BattlePage(ctx)
    for index in range(len(_SLOT_POSITIONS)):
        page.click_chapter_slot(index)

    assert control.clicks == list(_SLOT_POSITIONS)


def test_click_chapter_slot_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """索引超出可见槽位范围时直接报错，不点击。"""
    _stub_constants(monkeypatch)

    with pytest.raises(ValueError, match='章节槽位索引必须为 0-4'):
        BattlePage(ctx).click_chapter_slot(5)
    with pytest.raises(ValueError, match='章节槽位索引必须为 0-4'):
        BattlePage(ctx).click_chapter_slot(-1)

    assert control.clicks == []


def test_map_navigation_and_sortie_entry(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """翻页与出击按钮各点各的落点。"""
    _stub_constants(monkeypatch)

    page = BattlePage(ctx)
    page.click_map_next()
    page.click_map_prev()
    page.click_enter_sortie()

    assert control.clicks == [(0.31, 0.32), (0.41, 0.42), (0.51, 0.52)]
