"""模块功能：验证侧边栏检查器的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.sidebar 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import sidebar
from autowsgr.application.controller.sidebar import checker as sidebar_checker
from autowsgr.application.controller.sidebar.build import (
    check_build_page,
    check_dismantle_tab,
)
from autowsgr.application.controller.sidebar.build import checker as build_checker
from autowsgr.application.controller.sidebar.friend import check_friend_page
from autowsgr.application.controller.sidebar.friend import checker as friend_checker
from autowsgr.application.controller.sidebar.intensify import (
    check_intensify_page,
    check_remold_tab,
    check_skill_tab,
)
from autowsgr.application.controller.sidebar.intensify import (
    checker as intensify_checker,
)


if TYPE_CHECKING:
    import pytest


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    visible_roi: object | None,
) -> None:
    """用替身接管某个模块的识别入口，只让指定识别区域命中。"""

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        roi = options.get('roi')
        if isinstance(roi, tuple):
            matched = any(candidate is visible_roi for candidate in roi)
        else:
            matched = roi is visible_roi
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(module, 'expect_template', expect_template)


def test_sidebar_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """侧边栏模板命中时确认侧边栏展开。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.SIDEBAR_MAIN_ROI)

    assert sidebar.check_sidebar_page(object()) is True


def test_sidebar_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """侧边栏模板未命中时不算展开。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.BUILD_SUBMENU_ROI)

    assert sidebar.check_sidebar_page(object()) is False


def test_sidebar_absent_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """后识别：模板未命中时，期望收起为真。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.BUILD_SUBMENU_ROI)

    assert sidebar.check_sidebar_page(object(), absent=True) is True


def test_build_submenu_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """建造二级菜单模板命中时确认它弹出。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.BUILD_SUBMENU_ROI)

    assert sidebar.check_build_submenu(object()) is True


def test_build_submenu_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """建造二级菜单模板未命中时不算弹出。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.SIDEBAR_MAIN_ROI)

    assert sidebar.check_build_submenu(object()) is False


def test_intensify_submenu_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """强化二级菜单模板命中时确认它弹出。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.INTENSIFY_SUBMENU_ROI)

    assert sidebar.check_intensify_submenu(object()) is True


def test_intensify_submenu_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """强化二级菜单模板未命中时不算弹出。"""
    _install_recognition(monkeypatch, sidebar_checker, sidebar_checker.SIDEBAR_MAIN_ROI)

    assert sidebar.check_intensify_submenu(object()) is False


def test_friend_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """好友页面模板命中时确认在前台。"""
    _install_recognition(monkeypatch, friend_checker, friend_checker.FRIEND_TAB_ROI)

    assert check_friend_page(object()) is True


def test_friend_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """好友页面模板未命中时不算在前台。"""
    _install_recognition(monkeypatch, friend_checker, sidebar_checker.SIDEBAR_MAIN_ROI)

    assert check_friend_page(object()) is False


def test_build_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """建造页默认落在「建造」标签，模板命中即算到达。"""
    _install_recognition(monkeypatch, build_checker, build_checker.BUILD_TAB_ROI)

    assert check_build_page(object()) is True


def test_build_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """未落在建造标签时不算到达。"""
    _install_recognition(monkeypatch, build_checker, build_checker.DISMANTLE_TAB_ROI)

    assert check_build_page(object()) is False


def test_dismantle_tab_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """解体标签激活时确认切换成功。"""
    _install_recognition(monkeypatch, build_checker, build_checker.DISMANTLE_TAB_ROI)

    assert check_dismantle_tab(object()) is True


def test_intensify_page_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """改造页默认落在「强化」标签，模板命中即算到达。"""
    _install_recognition(monkeypatch, intensify_checker, intensify_checker.INTENSIFY_TAB_ROI)

    assert check_intensify_page(object()) is True


def test_intensify_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """未落在强化标签时不算到达。"""
    _install_recognition(monkeypatch, intensify_checker, intensify_checker.SKILL_TAB_ROI)

    assert check_intensify_page(object()) is False


def test_remold_and_skill_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """改造与技能标签各自能被确认。"""
    _install_recognition(monkeypatch, intensify_checker, intensify_checker.REMOLD_TAB_ROI)
    assert check_remold_tab(object()) is True
    assert check_skill_tab(object()) is False

    _install_recognition(monkeypatch, intensify_checker, intensify_checker.SKILL_TAB_ROI)
    assert check_skill_tab(object()) is True
    assert check_remold_tab(object()) is False
