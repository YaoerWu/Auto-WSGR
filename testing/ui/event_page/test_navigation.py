"""模块功能：检查活动入口导航边是否接入统一导航动作。

上层调用：
- pytest：验证导航图中的 HOME -> EVENT_MAP 边。

下层依赖：
- application.navigation.graph.common：提供公共导航边。
- application.navigation.event：提供活动入口导航动作。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from autowsgr.application.navigation import event as event_navigation
from autowsgr.application.navigation.graph.common import COMMON_EDGES
from autowsgr.common.types import PageName


if TYPE_CHECKING:
    import pytest


def test_home_event_edge_uses_navigation_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """HOME 到活动地图的导航边调用统一的活动导航动作。"""
    edge = next(
        item
        for item in COMMON_EDGES
        if item.source == PageName.HOME and item.target == PageName.EVENT_MAP
    )
    ctx = MagicMock()
    navigate = MagicMock()
    monkeypatch.setattr(event_navigation, 'navigate_to_event', navigate)

    edge.action(ctx)

    navigate.assert_called_once_with(ctx)
