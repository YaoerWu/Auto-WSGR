"""模块功能：验证出征页标签切换与返回的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie import page as sortie_page_module
from autowsgr.application.controller.sortie.page import SORTIE_TAB_LIST, SortiePage, SortieTab


if TYPE_CHECKING:
    from typing import Any

    import pytest


def _stub_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    """用可断言的落点替身接取出征页常量。"""
    monkeypatch.setattr(
        sortie_page_module,
        'constants',
        SimpleNamespace(
            TAB_POSITIONS={
                'sortie': (0.11, 0.12),
                'exercise': (0.21, 0.22),
                'expedition': (0.31, 0.32),
                'campaign': (0.41, 0.42),
                'decisive': (0.51, 0.52),
            },
            CLICK_BACK=(0.61, 0.62),
        ),
    )


def test_tab_list_matches_enum_order() -> None:
    """标签清单按枚举声明顺序展开，供调用方遍历。"""
    assert tuple(SortieTab) == SORTIE_TAB_LIST
    assert [tab.value for tab in SORTIE_TAB_LIST] == ['出征', '演习', '远征', '战役', '决战']


def test_go_to_clicks_each_tab_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """五个标签各自点击自己的落点。"""
    _stub_constants(monkeypatch)

    page = SortiePage(ctx)
    for tab in SORTIE_TAB_LIST:
        page.go_to(tab)

    assert control.clicks == [
        (0.11, 0.12),
        (0.21, 0.22),
        (0.31, 0.32),
        (0.41, 0.42),
        (0.51, 0.52),
    ]


def test_go_to_prefers_explicit_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """显式位置优先于常量表落点。"""
    _stub_constants(monkeypatch)

    SortiePage(ctx).go_to(SortieTab.EXERCISE, (0.7, 0.8))

    assert control.clicks == [(0.7, 0.8)]


def test_go_back_clicks_back_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """返回按钮点左上角落点。"""
    _stub_constants(monkeypatch)

    SortiePage(ctx).go_back()

    assert control.clicks == [(0.61, 0.62)]
