"""模块功能：验证推图活动 checker 的识别判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、NumPy、common.vision 结果类型和 checker.event。

边界：用替身接管识别入口，不加载模板图片、不初始化 OCR 模型、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from autowsgr.application.controller.event import stage_push
from autowsgr.application.controller.event.stage_push import checker as event_checker
from autowsgr.application.navigation.types import NavigationError
from autowsgr.application.ui import template
from autowsgr.common.vision import RecognitionResult


class _Match:
    """模板匹配结果替身。"""

    def __init__(self, matched: bool) -> None:
        self.matched = matched


class _Detection:
    """OCR 识别结果替身。"""

    def __init__(self, text: str) -> None:
        self.recognized_text = text


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    button_matches: tuple[bool, bool] = (False, False),
    map_texts: tuple[str, ...] = (),
    overlay_open: bool = False,
    stage_title_texts: tuple[str, ...] = (),
    entry_visible: bool = False,
) -> None:
    """用替身接管识别入口，按识别区域返回预设事实。"""
    screen = np.zeros((4, 4, 3), dtype=np.uint8)
    monkeypatch.setattr(template, 'load_ui_template', lambda *_args, **_kwargs: object())

    def expect_template(_ctx: object, **options: object) -> RecognitionResult[list[object]]:
        roi = options['roi']
        if roi is event_checker.HOME_ENTRY_ROI:
            return RecognitionResult(entry_visible, [_Match(entry_visible)], screen)
        if roi is event_checker.MODE_ROI:
            matches = [_Match(matched) for matched in button_matches]
            return RecognitionResult(any(button_matches), matches, screen)
        if roi is event_checker.SORTIE_PREPARE_ROI:
            return RecognitionResult(overlay_open, [_Match(overlay_open)], screen)
        raise AssertionError(f'未预期的模板识别区域: {roi!r}')

    def expect_ocr(_ctx: object, **options: object) -> RecognitionResult[list[object]]:
        roi = options['roi']
        if roi is event_checker.MAP_NAME_ROI:
            texts = map_texts
        elif roi is event_checker.STAGE_TITLE_ROI:
            texts = stage_title_texts
        else:
            raise AssertionError(f'未预期的 OCR 区域: {roi!r}')
        return RecognitionResult(bool(texts), [_Detection(text) for text in texts], screen)

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float] | None:
        roi = options['roi']
        if roi is event_checker.MODE_ROI:
            return (0.5, 0.5) if any(button_matches) else None
        if roi is event_checker.SORTIE_PREPARE_ROI:
            return (0.6, 0.7) if overlay_open else None
        raise AssertionError(f'未预期的模板中心区域: {roi!r}')

    # 读明细的入口仍挂在本模块；其余走共用入口。
    monkeypatch.setattr(event_checker, 'expect_template', expect_template)
    monkeypatch.setattr(event_checker, 'expect_ocr', expect_ocr)
    monkeypatch.setattr(event_checker, 'expect_template_center', expect_template_center)


def test_event_entry_reports_visible_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """首页入口模板命中时入口成立。"""
    _install_recognition(monkeypatch, entry_visible=True)

    assert stage_push.check_event_entry(object(), event_type='stage_push') is True


def test_event_rejects_other_activity() -> None:
    """其它活动玩法不属于本 checker 的入参。"""
    with pytest.raises(ValueError, match='当前 checker 不支持的活动玩法'):
        stage_push.check_event_entry(object(), event_type='assault')


def test_wait_event_mode_returns_once_mode_settled(monkeypatch: pytest.MonkeyPatch) -> None:
    """当前难度已经是目标难度时立刻返回。"""
    _install_recognition(monkeypatch, button_matches=(False, True), map_texts=('最强之舟',))

    assert (
        stage_push.wait_event_mode(
            object(), event_type='stage_push', mode=stage_push.EventMode.NORMAL, attempts=1
        )
        is True
    )


def test_wait_event_mode_gives_up_on_other_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """难度没切到目标值时重读用尽后放弃。"""
    _install_recognition(monkeypatch, button_matches=(False, True), map_texts=('最强之舟',))

    assert (
        stage_push.wait_event_mode(
            object(),
            event_type='stage_push',
            mode=stage_push.EventMode.HARD,
            attempts=1,
            interval_seconds=0.0,
        )
        is False
    )


def test_map_page_accepts_visible_mode_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """模式按钮还亮着 = 干净地图页。"""
    _install_recognition(monkeypatch, button_matches=(True, False))

    assert stage_push.check_event_map_page(object()) is True


def test_map_page_rejects_overlay_even_with_readable_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """浮窗压暗按钮时，读得到地图名也不算干净地图页。"""
    _install_recognition(monkeypatch, overlay_open=True, map_texts=('最强之舟',))

    assert stage_push.check_event_map_page(object()) is False


def test_map_page_accepts_normal_title_without_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮不命中且没有浮窗时，普通地图名说明困难尚未开放。"""
    _install_recognition(monkeypatch, map_texts=('最强之舟',))

    assert stage_push.check_event_map_page(object()) is True


def test_map_page_honours_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """absent 翻转断言方向。"""
    _install_recognition(monkeypatch, button_matches=(True, False))

    assert stage_push.check_event_map_page(object(), absent=True) is False


def test_map_state_resolves_hard_map_from_opposite_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮显示普通且标题为困难名时，当前是困难地图。"""
    _install_recognition(
        monkeypatch,
        button_matches=(True, False),
        map_texts=('最强之舟（困难）',),
    )

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.on_clean_map is True
    assert state.button_mode is stage_push.EventMode.NORMAL
    assert state.title_mode is stage_push.EventMode.HARD
    assert state.current_mode is stage_push.EventMode.HARD


def test_map_state_resolves_normal_map_from_opposite_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮显示困难且标题为普通名时，当前是普通地图。"""
    _install_recognition(
        monkeypatch,
        button_matches=(False, True),
        map_texts=('最强之舟',),
    )

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.button_mode is stage_push.EventMode.HARD
    assert state.title_mode is stage_push.EventMode.NORMAL
    assert state.current_mode is stage_push.EventMode.NORMAL


def test_map_state_reports_normal_when_hard_is_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有模式按钮且标题为普通名时，困难难度尚未开放。"""
    _install_recognition(monkeypatch, map_texts=('最强之舟',))

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.button_mode is None
    assert state.title_mode is stage_push.EventMode.NORMAL
    assert state.current_mode is stage_push.EventMode.NORMAL


def test_map_state_withholds_conclusion_on_conflicting_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮和标题互相矛盾时不下难度结论。"""
    _install_recognition(
        monkeypatch,
        button_matches=(True, False),
        map_texts=('最强之舟',),
    )

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.current_mode is None


def test_map_state_withholds_conclusion_on_sortie_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """节点浮窗打开时模式按钮失效，不下难度结论。"""
    _install_recognition(
        monkeypatch,
        overlay_open=True,
        map_texts=('最强之舟',),
        stage_title_texts=('Ex-7 天降火雨(困难)',),
    )

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.on_clean_map is False
    assert state.current_mode is None


def test_map_state_withholds_conclusion_when_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮和标题都读不到时只返回空事实。"""
    _install_recognition(monkeypatch)

    state = stage_push.read_event_map_state(object(), event_type='stage_push')

    assert state.on_clean_map is True
    assert state.button_mode is None
    assert state.title_mode is None
    assert state.current_mode is None


def test_sortie_prepare_matches_stage_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗标题命中目标关卡编号时准备页成立。"""
    _install_recognition(
        monkeypatch,
        overlay_open=True,
        stage_title_texts=('Ex-7 天降火雨(困难)',),
    )

    assert (
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX7')
        is True
    )


def test_sortie_prepare_matches_stage_name_when_number_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """标题编号丢失但章节名称命中时准备页仍然成立。"""
    _install_recognition(
        monkeypatch,
        overlay_open=True,
        stage_title_texts=('Ex 天降火雨（困难）',),
    )

    assert (
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX7')
        is True
    )


def test_sortie_prepare_rejects_other_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗标题指向其它章节时准备页不成立。"""
    _install_recognition(
        monkeypatch,
        overlay_open=True,
        stage_title_texts=('Ex-1 天降火雨',),
    )

    assert (
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX7')
        is False
    )


def test_sortie_prepare_keeps_modes_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一格的两个难度靠"困难"二字区分：普通判据不认困难浮窗，困难判据认。"""
    _install_recognition(
        monkeypatch,
        overlay_open=True,
        stage_title_texts=('Ex-7 天降火雨（困难）',),
    )

    assert (
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX1')
        is False
    )
    assert (
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX7')
        is True
    )


def test_sortie_prepare_rejects_unknown_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """本期数据里没有的章节属于入参错误。"""
    _install_recognition(monkeypatch)

    with pytest.raises(ValueError, match='章节标识超出范围'):
        stage_push.check_event_sortie_prepare(object(), event_type='stage_push', stage='EX99')


def test_read_event_binding_rejects_missing_facts() -> None:
    """任务没绑定活动玩法或章节时，读取入口抛导航错误。"""
    with pytest.raises(NavigationError, match='event_type'):
        stage_push.read_event_type(SimpleNamespace(read_event_type=lambda: None))

    with pytest.raises(NavigationError, match='event_stage'):
        stage_push.read_event_stage(SimpleNamespace(read_event_stage=lambda: None))
