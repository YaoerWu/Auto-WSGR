"""模块功能：验证主页检查器的浮窗判层、每日标记与落点读取流程。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.home.checker 与 dispatch.session 事实。
边界：用替身接管识别入口与模板加载，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.controller import home
from autowsgr.application.controller.home import checker as home_checker
from autowsgr.application.controller.home import constants
from autowsgr.application.navigation.types import PageName
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
    """每个场景用一份干净的会话状态，避免「今天不会再弹」标记跨场景串味。"""
    session = SessionState()
    monkeypatch.setattr(home_checker, 'get_session', lambda: session)
    return session


def test_read_home_layer_stacks_visible_layers_and_skips_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次读帧按由深到浅报出同时可见的层；已处理过的浮窗不再参与判层。"""
    _install_recognition(monkeypatch, home_visible=True)
    _fresh_session(monkeypatch)
    assert home.read_home_layer(object()) == (PageName.HOME,)

    _install_recognition(monkeypatch, home_visible=True, reward_matches=(True, False))
    _fresh_session(monkeypatch)
    assert home.read_home_layer(object()) == (PageName.HOME_REWARD, PageName.HOME)

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

    _install_recognition(monkeypatch)
    _fresh_session(monkeypatch)
    assert home.read_home_layer(object()) == ()

    _install_recognition(monkeypatch, home_visible=True, news_matches=(True, True, False))
    session = _fresh_session(monkeypatch)
    session.mark_popup_settled(DailyPopup.NEWS)
    assert home.read_home_layer(object()) == (PageName.HOME,)


def test_news_overlay_reads_checked_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """公告浮窗一次读取同时给出浮窗状态与勾选状态，缺失或已处理时都当它不在。"""
    _install_recognition(monkeypatch, news_matches=(True, True, False))
    _fresh_session(monkeypatch)
    checked = home.read_news_overlay(object())
    assert (checked.matched, checked.checked) == (True, True)

    _install_recognition(monkeypatch, news_matches=(True, False, True))
    _fresh_session(monkeypatch)
    unchecked = home.read_news_overlay(object())
    assert (unchecked.matched, unchecked.checked) == (True, False)

    _install_recognition(monkeypatch)
    _fresh_session(monkeypatch)
    absent = home.read_news_overlay(object())
    assert (absent.matched, absent.checked) == (False, None)

    _install_recognition(monkeypatch, news_matches=(True, False, True))
    session = _fresh_session(monkeypatch)
    session.mark_popup_settled(DailyPopup.NEWS)
    settled = home.read_news_overlay(object())
    assert (settled.matched, settled.checked) == (False, None)


def test_reward_overlay_reads_text_or_button_and_confirm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """奖励文字或领取按钮命中即算浮窗存在；确认浮窗盖上来时奖励层不再算当前。"""
    _install_recognition(monkeypatch, reward_matches=(True, False))
    _fresh_session(monkeypatch)
    assert home.check_home_reward_overlay(object()) is True

    _install_recognition(monkeypatch, confirm_visible=True)
    _fresh_session(monkeypatch)
    assert home.check_home_reward_overlay(object()) is False
    assert home.check_home_reward_confirm(object()) is True

    _install_recognition(monkeypatch, reward_matches=(True, True))
    session = _fresh_session(monkeypatch)
    session.mark_popup_settled(DailyPopup.REWARD)
    assert home.check_home_reward_overlay(object()) is False


def test_popups_are_settled_only_on_a_clean_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """三个浮窗都标记后才算今天处理完；只有干净主页到达时才批量写入标记。"""
    session = _fresh_session(monkeypatch)

    assert home_checker.popups_all_settled() is False
    for popup in DailyPopup:
        session.mark_popup_settled(popup)
    assert home_checker.popups_all_settled() is True

    session = _fresh_session(monkeypatch)
    home_checker.mark_popups_settled(object())
    assert all(not session.popup_settled(popup) for popup in DailyPopup)

    session.push_page(PageName.SORTIE_MAP.value)
    monkeypatch.setattr(
        home_checker,
        'read_home_layer',
        lambda _ctx, **_options: (PageName.HOME_REWARD, PageName.HOME),
    )
    home_checker.mark_popups_settled(object())
    assert all(not session.popup_settled(popup) for popup in DailyPopup)

    monkeypatch.setattr(
        home_checker,
        'read_home_layer',
        lambda _ctx, **_options: (PageName.HOME,),
    )
    home_checker.mark_popups_settled(object())
    assert all(session.popup_settled(popup) for popup in DailyPopup)


def test_overlay_center_readers_pass_their_rois(monkeypatch: pytest.MonkeyPatch) -> None:
    """三个浮窗按钮的落点读取各自绑定自己的区域，且只读当前一帧。"""
    calls: list[dict[str, object]] = []

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float]:
        calls.append(options)
        return (0.5, 0.5)

    monkeypatch.setattr(home_checker, 'load_ui_template', lambda *_args, **_kwargs: object())
    monkeypatch.setattr(home_checker, 'expect_template_center', expect_template_center)

    assert home.read_news_checkbox_center(object()) == (0.5, 0.5)
    assert home.read_reward_claim_center(object()) == (0.5, 0.5)
    assert home.read_reward_confirm_center(object()) == (0.5, 0.5)

    rois = [options['roi'] for options in calls]
    assert rois == [
        constants.NEWS_CHECKBOX_ROI,
        constants.REWARD_CLAIM_BUTTON_ROI,
        constants.REWARD_CONFIRM_BUTTON_ROI,
    ]
    assert all(options['attempts'] == 1 for options in calls)
