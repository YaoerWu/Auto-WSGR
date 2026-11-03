"""模块功能：验证好友页面识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sidebar.friend.checker 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller.sidebar.friend import (
    check_friend_page,
)
from autowsgr.application.controller.sidebar.friend import (
    checker as friend_checker,
)


if TYPE_CHECKING:
    import pytest


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    visible_rois: tuple[object, ...],
) -> list[dict[str, object]]:
    """让列出的识别区域命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        roi = options.get('roi')
        regions = roi if isinstance(roi, tuple) else (roi,)
        matched = any(region in visible_rois for region in regions)
        return SimpleNamespace(
            satisfied=(not matched) if options.get('absent') else matched,
        )

    monkeypatch.setattr(friend_checker, 'expect_template', expect_template)
    return calls


def test_friend_page_visible_by_first_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """「好友」页签命中即算在好友页。"""
    calls = _install_recognition(monkeypatch, (friend_checker.constants.FRIEND_TAB_ROI,))

    assert check_friend_page(object()) is True
    assert calls[0]['roi'] == (
        friend_checker.constants.FRIEND_TAB_ROI,
        friend_checker.constants.FRIEND_ADD_TAB_ROI,
    )
    assert calls[0]['attempts'] == 5
    assert calls[0]['interval_seconds'] == 1.0


def test_friend_page_visible_by_add_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """「添加」页签命中同样算在好友页。"""
    _install_recognition(monkeypatch, (friend_checker.constants.FRIEND_ADD_TAB_ROI,))

    assert check_friend_page(object()) is True


def test_friend_page_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """两个页签都不在时不算在前台。"""
    _install_recognition(monkeypatch, ())

    assert check_friend_page(object()) is False


def test_friend_page_absent_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """后识别：两个页签都不在时期待离开成立。"""
    _install_recognition(monkeypatch, ())

    assert check_friend_page(object(), absent=True) is True
