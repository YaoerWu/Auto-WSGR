"""模块功能：验证侧边栏检查器的识别判定契约。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.sidebar.checker 与 vision 识别入口。
边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import sidebar
from autowsgr.application.controller.sidebar import checker as sidebar_checker


if TYPE_CHECKING:
    import pytest


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    visible_roi: object | None,
) -> list[dict[str, object]]:
    """用替身接管识别入口，只让指定识别区域命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        roi = options.get('roi')
        matched = roi is visible_roi
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(sidebar_checker, 'expect_template', expect_template)
    return calls


def test_sidebar_page_and_submenus_follow_their_own_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三层判层各看自己的区域：主栏、建造子菜单与强化子菜单互不串判。"""
    calls = _install_recognition(monkeypatch, sidebar_checker.constants.SIDEBAR_MAIN_ROI)

    assert sidebar.check_sidebar_page(object()) is True
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0
    assert sidebar.check_build_submenu(object()) is False
    assert sidebar.check_intensify_submenu(object()) is False

    _install_recognition(monkeypatch, sidebar_checker.constants.BUILD_SUBMENU_ROI)

    assert sidebar.check_sidebar_page(object()) is False
    assert sidebar.check_sidebar_page(object(), absent=True) is True
    assert sidebar.check_build_submenu(object()) is True
    assert sidebar.check_intensify_submenu(object()) is False

    _install_recognition(monkeypatch, sidebar_checker.constants.INTENSIFY_SUBMENU_ROI)

    assert sidebar.check_intensify_submenu(object()) is True
    assert sidebar.check_build_submenu(object()) is False
