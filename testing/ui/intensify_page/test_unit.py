"""模块功能：验证强化页面的导航边界。

上层调用：
- pytest：执行强化页面的无设备单元验证。

下层依赖：
- application.ui.controller.sidebar.intensify_page：提供强化页面导航控制器。

边界：
本模块只使用 mock 验证页面契约，不连接真实设备或修改运行时数据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from autowsgr.application.controller.sidebar.intensify import IntensifyPage
from autowsgr.application.ui.controller.sidebar.intensify_page import (
    constants,
    page,
)
from autowsgr.common.types import PageName


if TYPE_CHECKING:
    import pytest


def test_check_current_page_delegates_to_intensify_page_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面检查使用通用强化页面组识别。"""
    checker = MagicMock(return_value='matched')
    monkeypatch.setattr(page, 'check_tabbed_page', checker)
    screen = object()

    assert IntensifyPage.check_current_page(screen) == 'matched'
    checker.assert_called_once_with(screen, page.TabbedPageType.INTENSIFY)


def test_go_back_uses_sidebar_navigation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面返回使用校准坐标并等待侧边栏终态。"""
    ctx = MagicMock()
    wait_for_page = MagicMock()
    monkeypatch.setattr(page, 'click_and_wait_for_page', wait_for_page)

    IntensifyPage(ctx).go_back()

    wait_for_page.assert_called_once()
    assert wait_for_page.call_args.args[0] is ctx.ctrl
    assert wait_for_page.call_args.kwargs['click_coord'] == constants.CLICK_BACK
    assert wait_for_page.call_args.kwargs['source'] == PageName.INTENSIFY
    assert wait_for_page.call_args.kwargs['target'] == PageName.SIDEBAR


def test_page_exposes_navigation_only() -> None:
    """未完成的强化业务不会形成页面公开方法。"""
    assert not hasattr(IntensifyPage, 'select_tab')
    assert not hasattr(IntensifyPage, 'read_active_tab')
    assert not hasattr(page, 'IntensifyTab')
