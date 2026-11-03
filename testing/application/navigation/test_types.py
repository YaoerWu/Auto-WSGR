"""模块功能：验证导航契约里的页面名、目标、标签与错误类型。

直接调用方：项目测试运行器。

直接依赖：navigation.types 与 common.system.errors。

边界：只验证数据契约，不触发导航、不访问设备。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from autowsgr.application.navigation.types import (
    ManualUpdateRequiredError,
    NavigationError,
    NavTab,
    NavTarget,
    PageName,
)
from autowsgr.common.system.errors import ApplicationError


def test_page_name_behaves_like_text() -> None:
    """页面名可与字符串直接比较，也能按中文值反查。"""
    assert PageName.HOME == '主页面'
    assert PageName('出征页面') is PageName.SORTIE_MAP
    assert PageName.SORTIE_MAP.value == '出征页面'


def test_nav_target_defaults_confirm_and_tab() -> None:
    """目标默认需要到达确认，且不强制切标签。"""
    target = NavTarget(PageName.HOME, lambda _ctx: None, description='进入主页')

    assert target.confirm is True
    assert target.tab is None
    assert target.description == '进入主页'


def test_nav_target_is_frozen() -> None:
    """目标是不可变数据，避免执行途中被改写。"""
    target = NavTarget(PageName.HOME, lambda _ctx: None)

    with pytest.raises(FrozenInstanceError):
        target.target = PageName.MISSION  # type: ignore[misc]


def test_nav_tab_carries_click_and_checker() -> None:
    """标签同时给出「怎么点」和「怎么确认」。"""
    tab = NavTab(lambda _ctx: None, lambda _ctx: True, '出征')

    assert tab.checker(None) is True
    assert tab.description == '出征'


def test_manual_update_error_is_navigation_error() -> None:
    """需要人工更新属于导航错误的一种，但可被单独捕获。"""
    assert issubclass(ManualUpdateRequiredError, NavigationError)
    assert issubclass(NavigationError, ApplicationError)
