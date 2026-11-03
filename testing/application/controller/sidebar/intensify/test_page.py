"""模块功能：验证改造页标签切换与返回的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.intensify.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.sidebar.intensify import page as intensify_page_module
from autowsgr.application.controller.sidebar.intensify.page import IntensifyPage, IntensifyTab


def _stub_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    """用可断言的落点替身接管改造页常量。"""
    monkeypatch.setattr(
        intensify_page_module,
        'constants',
        SimpleNamespace(
            TAB_POSITIONS={
                'intensify': (0.11, 0.12),
                'remold': (0.21, 0.22),
                'skill': (0.31, 0.32),
            },
            CLICK_BACK=(0.41, 0.42),
        ),
    )


def test_go_to_tab_clicks_each_tab_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """三个标签各自点击自己的落点。"""
    _stub_constants(monkeypatch)

    page = IntensifyPage(ctx)
    for tab in IntensifyTab:
        page.go_to_tab(tab)

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22), (0.31, 0.32)]


def test_go_to_tab_rejects_unknown_tab(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """常量表里没有的标签直接报错，不点任何位置。"""
    monkeypatch.setattr(
        intensify_page_module,
        'constants',
        SimpleNamespace(TAB_POSITIONS={}, CLICK_BACK=(0.41, 0.42)),
    )

    with pytest.raises(ValueError, match='改造页没有该标签的落点'):
        IntensifyPage(ctx).go_to_tab(IntensifyTab.INTENSIFY)

    assert control.clicks == []


def test_go_back_clicks_back_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """返回按钮点左上角落点。"""
    _stub_constants(monkeypatch)

    IntensifyPage(ctx).go_back()

    assert control.clicks == [(0.41, 0.42)]
