"""模块功能：验证侧边栏一级条目跳转与收起的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.sidebar import page as sidebar_page
from autowsgr.application.controller.sidebar.page import SidebarPage, SidebarTarget
from autowsgr.application.navigation.types import PageName


def _stub_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    """用可断言的落点替身接管侧边栏常量。"""
    monkeypatch.setattr(
        sidebar_page,
        'constants',
        SimpleNamespace(
            NAV_POSITIONS={
                'build': (0.11, 0.12),
                'intensify': (0.21, 0.22),
                'friend': (0.31, 0.32),
            },
            SUBMENU_POSITIONS={
                'build': (0.41, 0.42),
                'intensify': (0.51, 0.52),
            },
            CLICK_CLOSE=(0.61, 0.62),
        ),
    )


def test_target_page_names_cover_the_navigation_map() -> None:
    """三个一级条目各自映射到导航图里的页面名称。"""
    assert {target: target.page_name for target in SidebarTarget} == {
        SidebarTarget.BUILD: PageName.BUILD,
        SidebarTarget.INTENSIFY: PageName.INTENSIFY,
        SidebarTarget.FRIEND: PageName.FRIEND,
    }


def test_go_to_clicks_configured_positions(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """进入每个一级条目时点击它自己的落点。"""
    _stub_constants(monkeypatch)

    page = SidebarPage(ctx)
    for target in SidebarTarget:
        page.go_to(target)

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22), (0.31, 0.32)]


def test_go_to_submenu_clicks_first_item(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """建造与强化点二级菜单首项。"""
    _stub_constants(monkeypatch)

    page = SidebarPage(ctx)
    page.go_to_submenu(SidebarTarget.BUILD)
    page.go_to_submenu(SidebarTarget.INTENSIFY)

    assert control.clicks == [(0.41, 0.42), (0.51, 0.52)]


def test_go_to_submenu_rejects_target_without_menu(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """好友没有二级菜单，直接报错且不点击。"""
    _stub_constants(monkeypatch)

    with pytest.raises(ValueError, match='侧边栏没有该目标的二级菜单落点'):
        SidebarPage(ctx).go_to_submenu(SidebarTarget.FRIEND)

    assert control.clicks == []


def test_go_back_closes_sidebar(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """收起侧边栏点空白处。"""
    _stub_constants(monkeypatch)

    SidebarPage(ctx).go_back()

    assert control.clicks == [(0.61, 0.62)]
