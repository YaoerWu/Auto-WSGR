"""模块功能：验证好友页面标签切换与返回的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.friend.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sidebar.friend import page as friend_page_module
from autowsgr.application.controller.sidebar.friend.page import FriendPage


if TYPE_CHECKING:
    import pytest


def test_clicks_tab_and_back(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """切回好友标签点页签落点，返回点左上角落点。"""
    monkeypatch.setattr(
        friend_page_module,
        'constants',
        SimpleNamespace(CLICK_TAB=(0.11, 0.12), CLICK_BACK=(0.21, 0.22)),
    )

    page = FriendPage(ctx)
    page.go_to_tab()
    page.go_back()

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22)]
