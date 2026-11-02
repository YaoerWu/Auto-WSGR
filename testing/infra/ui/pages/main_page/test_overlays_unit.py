"""主页面每日浮层操作的无设备单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from autowsgr.application.controller.home import HomePage
from autowsgr.application.ui.controller.home.main_page import (
    operations,
    recognition,
)
from autowsgr.application.ui.controller.home.main_page import page as page_module
from autowsgr.application.ui.controller.home.main_page.constants import DISMISS_POSITIONS
from autowsgr.common.vision import ImageChecker


@pytest.mark.parametrize('second_confirmed', [False, True])
def test_dismiss_sign_handles_optional_second_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    second_confirmed: bool,
) -> None:
    """签到首次确认必须处理，第二段确认存在时继续点击。"""
    ctrl = MagicMock()
    confirm = MagicMock(side_effect=[True, second_confirmed])
    sleep = MagicMock()
    monkeypatch.setattr(operations, 'confirm_operation', confirm)
    monkeypatch.setattr(operations.time, 'sleep', sleep)

    operations.dismiss_sign(ctrl)

    ctrl.click.assert_called_once_with(*DISMISS_POSITIONS['sign_confirm'])
    assert confirm.call_args_list == [
        call(ctrl, must_confirm=True, timeout=operations._SIGN_CONFIRM_TIMEOUT),
        call(ctrl, must_confirm=False, timeout=operations._SIGN_CONFIRM_TIMEOUT),
    ]
    sleep.assert_called_once_with(operations._SIGN_CONFIRM_WAIT)


def test_dismiss_current_overlay_processes_news_before_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每日公告关闭后重新识别并处理每日签到。"""
    ctrl = MagicMock()
    overlays = MagicMock(
        side_effect=[recognition.OverlayKind.NEWS, recognition.OverlayKind.SIGN, None]
    )
    news = MagicMock()
    sign = MagicMock()
    monkeypatch.setattr(page_module.recognition, 'read_overlay', overlays)
    monkeypatch.setattr(page_module.operations, 'dismiss_news', news)
    monkeypatch.setattr(page_module.operations, 'dismiss_sign', sign)

    assert HomePage(SimpleNamespace(ctrl=ctrl)).dismiss_current_overlay() is True

    news.assert_called_once_with(ctrl)
    sign.assert_called_once_with(ctrl)


@pytest.mark.parametrize(
    ('template_name', 'expected'),
    [
        ('overlay_news', recognition.OverlayKind.NEWS),
        ('overlay_sign', recognition.OverlayKind.SIGN),
        ('overlay_booking', recognition.OverlayKind.BOOKING),
        ('overlay_user_info', recognition.OverlayKind.USER_INFO),
    ],
)
def test_read_overlay_uses_templates(
    monkeypatch: pytest.MonkeyPatch,
    *,
    template_name: str,
    expected: recognition.OverlayKind,
) -> None:
    """浮层检测改用图像模板匹配 (含 USER_INFO 新增分支)。"""
    monkeypatch.setattr(
        ImageChecker,
        'find_any',
        lambda _s, templates, **_k: next(
            (
                SimpleNamespace(template_name=template.name, confidence=1.0)
                for template in templates
                if template.name == template_name
            ),
            None,
        ),
    )
    assert recognition.read_overlay(MagicMock()) is expected


def test_read_overlay_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """无浮层命中时返回 None。"""
    monkeypatch.setattr(ImageChecker, 'find_any', lambda *_a, **_k: None)
    assert recognition.read_overlay(MagicMock()) is None
