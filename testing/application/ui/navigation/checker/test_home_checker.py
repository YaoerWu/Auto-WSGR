"""模块功能：验证主页检查器的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.home 与 session 事实。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.ui.navigation.checker import home
from autowsgr.application.ui.navigation.checker.home import checker as home_checker
from autowsgr.application.ui.navigation.types import PageName
from autowsgr.dispatch.session import DailyPopup, SessionState


if TYPE_CHECKING:
    import pytest


class _Match:
    """模板匹配结果替身。"""

    def __init__(self, matched: bool) -> None:
        self.matched = matched


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    home_visible: bool = False,
    news_matches: tuple[bool, bool, bool] = (False, False, False),
    reward_matches: tuple[bool, bool] = (False, False),
    confirm_visible: bool = False,
) -> None:
    """用替身接管一帧读取，按顺序返回七个模板的命中状态。"""
    monkeypatch.setattr(home_checker, 'load_ui_template', lambda *_args, **_kwargs: object())

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        template = options.get('template')
        if isinstance(template, tuple) and len(template) == 7:
            flags = (home_visible, *news_matches, *reward_matches, confirm_visible)
            return SimpleNamespace(
                satisfied=any(flags),
                observation=[_Match(flag) for flag in flags],
            )
        if isinstance(template, tuple) and len(template) == 2:
            # 奖励浮窗：只读奖励文字和领取按钮。
            return SimpleNamespace(
                satisfied=any(reward_matches),
                observation=[_Match(flag) for flag in reward_matches],
            )
        # 确认按钮：单独一个模板。
        return SimpleNamespace(
            satisfied=confirm_visible,
            observation=[_Match(confirm_visible)],
        )

    monkeypatch.setattr(home_checker, 'expect_template', expect_template)


def _fresh_session(monkeypatch: pytest.MonkeyPatch) -> SessionState:
    """每个用例用一份干净的会话状态，避免「今天不会再弹」标记跨用例串味。"""
    session = SessionState()
    monkeypatch.setattr(home_checker, 'get_session', lambda: session)
    return session


def test_read_home_layer_returns_clean_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """只有主页模板命中时当前层是主页。"""
    _install_recognition(monkeypatch, home_visible=True)
    _fresh_session(monkeypatch)

    assert home.read_home_layer(object()) == (PageName.HOME,)


def test_read_home_layer_returns_reward_when_overlay_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """奖励浮窗命中时当前层是奖励，背后的主页仍在画面里。"""
    _install_recognition(monkeypatch, home_visible=True, reward_matches=(True, False))
    _fresh_session(monkeypatch)

    assert home.read_home_layer(object()) == (PageName.HOME_REWARD, PageName.HOME)


def test_read_home_layer_prefers_confirm_when_stacked(monkeypatch: pytest.MonkeyPatch) -> None:
    """确认浮窗盖在奖励上时三层从深到浅都报出来。"""
    _install_recognition(
        monkeypatch,
        home_visible=True,
        reward_matches=(True, True),
        confirm_visible=True,
    )
    _fresh_session(monkeypatch)

    assert home.read_home_layer(object()) == (
        PageName.HOME_REWARD_CONFIRM,
        PageName.HOME_REWARD,
        PageName.HOME,
    )


def test_read_home_layer_returns_none_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一个模板都没命中时没有任何层。"""
    _install_recognition(monkeypatch)
    _fresh_session(monkeypatch)

    assert home.read_home_layer(object()) == ()


def test_read_home_layer_skips_settled_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    """已处理过的浮窗不再参与判层。"""
    _install_recognition(monkeypatch, home_visible=True, news_matches=(True, True, False))
    session = _fresh_session(monkeypatch)
    session.mark_popup_settled(DailyPopup.NEWS)

    assert home.read_home_layer(object()) == (PageName.HOME,)


def test_news_overlay_reads_checked_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """公告浮窗一次读取同时给出浮窗状态和已勾选状态。"""
    _install_recognition(monkeypatch, news_matches=(True, True, False))

    state = home.read_news_overlay(object())

    assert state.matched is True
    assert state.checked is True


def test_news_overlay_reads_unchecked_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """勾选框未勾选时给出未勾选事实。"""
    _install_recognition(monkeypatch, news_matches=(True, False, True))

    state = home.read_news_overlay(object())

    assert state.matched is True
    assert state.checked is False


def test_news_overlay_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """三个模板都没命中时公告浮窗不存在。"""
    _install_recognition(monkeypatch)

    state = home.read_news_overlay(object())

    assert state.matched is False
    assert state.checked is None


def test_reward_overlay_matches_text_or_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """奖励文字命中即算奖励浮窗存在。"""
    _install_recognition(monkeypatch, reward_matches=(True, False))

    assert home.check_home_reward_overlay(object()) is True


def test_reward_overlay_absent_and_confirm_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    """奖励浮窗不存在的同时确认浮窗存在时，各自如实返回。"""
    _install_recognition(monkeypatch, confirm_visible=True)

    assert home.check_home_reward_overlay(object()) is False
    assert home.check_home_reward_confirm(object()) is True
