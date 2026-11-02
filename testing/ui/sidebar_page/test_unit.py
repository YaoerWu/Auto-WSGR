"""模块功能：验证侧边栏与好友页面控制器的点击落点。

直接调用方：项目测试运行器。

直接依赖：pytest、控制器与常量。

边界：用设备替身记录点击落点，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.sidebar import (
    SidebarPage,
    SidebarTarget,
)
from autowsgr.application.controller.sidebar.friend import FriendPage
from autowsgr.application.ui.controller.sidebar.friend_page import constants as friend_constants
from autowsgr.application.ui.controller.sidebar.main_page import constants as sidebar_constants
from autowsgr.application.navigation.types import PageName


class _Ctrl:
    """设备服务替身，记录点击落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))


def _ctx() -> Any:
    """构造带设备替身的上下文。"""
    return SimpleNamespace(runtime=SimpleNamespace(ctrl=_Ctrl()))


def test_sidebar_target_page_names() -> None:
    """三个一级条目各自映射到对应页面。"""
    assert SidebarTarget.BUILD.page_name is PageName.BUILD
    assert SidebarTarget.INTENSIFY.page_name is PageName.INTENSIFY
    assert SidebarTarget.FRIEND.page_name is PageName.FRIEND


@pytest.mark.parametrize(
    ('target', 'position'),
    [
        (SidebarTarget.BUILD, (0.1437, 0.3701)),
        (SidebarTarget.INTENSIFY, (0.1434, 0.5000)),
        (SidebarTarget.FRIEND, (0.1426, 0.7549)),
    ],
)
def test_sidebar_go_to_clicks_entry(target: SidebarTarget, position: tuple[float, float]) -> None:
    """一级条目按校准落点点击。"""
    ctx = _ctx()
    page = SidebarPage(ctx)

    page.go_to(target)

    assert ctx.runtime.ctrl.clicks == [position]
    assert sidebar_constants.NAV_POSITIONS[target.name.lower()] == position


def test_sidebar_go_back_clicks_blank_area() -> None:
    """关闭侧边栏点中部空白处。"""
    ctx = _ctx()
    page = SidebarPage(ctx)

    page.go_back()

    assert ctx.runtime.ctrl.clicks == [sidebar_constants.CLICK_CLOSE]


def test_friend_go_back_clicks_back_button() -> None:
    """好友页返回点左上角箭头，与出征页共用同一落点。"""
    ctx = _ctx()
    page = FriendPage(ctx)

    page.go_back()

    assert ctx.runtime.ctrl.clicks == [friend_constants.CLICK_BACK]
