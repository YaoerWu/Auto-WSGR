"""模块功能：验证登录 checker 的画面判断与参数传递。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.login.checker 与 vision 识别入口。

边界：用替身接管识别函数，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from autowsgr.application.controller.login import checker
from autowsgr.common.vision import Template


# 导航确认入口有自己的默认节奏（等弹层动画），其余入口保持单帧。
_NAV_CONFIRM_ENTRIES = {'check_login_page', 'check_server_select'}

_SCREEN_ENTRIES = [
    ('check_black_screen', 'expect_template'),
    ('check_update_prompt', 'expect_ocr'),
    ('check_loading', 'expect_ocr'),
    ('check_login_page', 'expect_template'),
    ('check_server_select', 'expect_template'),
]

# 模板入口与它们各自要交给能力层的模板个数。
_TEMPLATE_ENTRIES = [
    ('check_black_screen', 1),
    ('check_login_page', 2),
    ('check_server_select', 1),
]


def _capture(monkeypatch: pytest.MonkeyPatch, attr: str) -> dict[str, Any]:
    """用替身接管识别入口并记录调用参数。"""
    captured: dict[str, Any] = {}

    def fake(_ctx: object, *args: object, **options: object) -> SimpleNamespace:
        captured['args'] = args
        captured['options'] = options
        return SimpleNamespace(satisfied=True)

    monkeypatch.setattr(checker, attr, fake)
    return captured


def test_screen_entries_bind_vision_options_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五个画面入口把节奏原样传下去；不传参数时按各入口自己的默认节奏做前识别。"""
    for entry, target in _SCREEN_ENTRIES:
        captured = _capture(monkeypatch, target)
        result = getattr(checker, entry)(
            object(),
            absent=True,
            attempts=120,
            interval_seconds=1.0,
        )
        assert result is True
        options = captured['options']
        assert options['absent'] is True
        assert options['attempts'] == 120
        assert options['interval_seconds'] == 1.0

        captured = _capture(monkeypatch, target)
        assert getattr(checker, entry)(object()) is True
        defaults = captured['options']
        assert defaults['absent'] is False
        assert defaults['attempts'] == (10 if entry in _NAV_CONFIRM_ENTRIES else 1)
        assert defaults['interval_seconds'] == 0.5


def test_text_and_template_entries_carry_their_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文本入口比对约定 OCR 文本与区域；模板入口交出的已是加载好的 Template。"""
    captured = _capture(monkeypatch, 'expect_ocr')
    checker.check_update_prompt(object())
    assert captured['options']['expect'] == checker.UPDATE_PROMPT_TEXT
    assert captured['options']['roi'] is checker.UPDATE_PROMPT_ROI
    assert captured['options']['recognition_profile'] == 'single_line'

    checker.check_loading(object())
    assert captured['options']['expect'] == checker.LOADING_TEXT
    assert captured['options']['roi'] is checker.PROGRESS_TEXT_ROI

    for entry, expected_count in _TEMPLATE_ENTRIES:
        captured = _capture(monkeypatch, 'expect_template')
        assert getattr(checker, entry)(object()) is True
        templates = captured['options']['template']
        if expected_count == 1:
            templates = (templates,)
        assert len(templates) == expected_count
        assert all(isinstance(item, Template) for item in templates)


def test_server_lookup_uses_ocr_then_static_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """区服定位按列表顺序逐条命中；失败时退回静态映射；未知区服名直接报错。"""
    calls: list[object] = []

    def fake_expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        roi = options.get('roi')
        calls.append(roi)
        return SimpleNamespace(satisfied=roi is checker.SERVER_NAME_ROIS[2])

    monkeypatch.setattr(checker, 'expect_ocr', fake_expect_ocr)

    assert checker.read_server_position(object(), '昆西') == 2
    assert calls == list(checker.SERVER_NAME_ROIS[:3])

    monkeypatch.setattr(
        checker,
        'expect_ocr',
        lambda _ctx, **_options: SimpleNamespace(satisfied=False),
    )
    assert checker.read_server_position(object(), '昆西') is None

    monkeypatch.setattr(checker, 'read_server_position', lambda _ctx, _name: None)
    assert checker.read_server_index(object(), '昆西') == checker.get_server_index('昆西')

    with pytest.raises(ValueError, match='not in'):
        checker.get_server_index('不存在')


def test_center_readers_bind_their_rois(monkeypatch: pytest.MonkeyPatch) -> None:
    """两个入口的落点读取各自绑定自己的模板与区域。"""
    calls: list[dict[str, object]] = []

    def fake_center(_ctx: object, **options: object) -> tuple[float, float]:
        calls.append(options)
        return (0.5, 0.5)

    monkeypatch.setattr(checker, 'expect_template_center', fake_center)

    assert checker.read_enter_button_center(object()) == (0.5, 0.5)
    assert checker.read_switch_entry_center(object()) == (0.5, 0.5)
    assert [options['roi'] for options in calls] == [
        checker.ENTER_BUTTON_ROI,
        checker.SWITCH_ENTRY_ROI,
    ]
    assert all(options['attempts'] == 1 for options in calls)
