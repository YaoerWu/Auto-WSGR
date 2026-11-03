"""模块功能：验证军阶室二级页进入技能列表的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.backyard.rank_room.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.backyard.rank_room import page as rank_room_page
from autowsgr.application.controller.backyard.rank_room.page import RankRoomPage


if TYPE_CHECKING:
    import pytest


def test_go_to_skill_list_clicks_configured_position(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """技能列表入口点击常量表里的三级页落点。"""
    monkeypatch.setattr(
        rank_room_page,
        'constants',
        SimpleNamespace(CLICK_RANK_SKILL_LIST=(0.7, 0.3)),
    )

    RankRoomPage(ctx).go_to_skill_list()

    assert control.clicks == [(0.7, 0.3)]
