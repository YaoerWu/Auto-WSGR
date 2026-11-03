"""模块功能：验证战术支援按钮与浮窗的识别契约。

直接调用方：项目测试运行器。
直接依赖：pytest、controller.sortie.battle_preparation.tactical_support.checker 与
vision 识别入口。
边界：用替身接管模板加载与两路识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy
import pytest

from autowsgr.application.controller.sortie.battle_preparation.tactical_support import (
    checker as support_checker,
)
from autowsgr.application.controller.sortie.battle_preparation.tactical_support import (
    constants,
    read_tactical_support,
    read_tactical_support_button_center,
)
from autowsgr.common.vision import TextDetection


if TYPE_CHECKING:
    from autowsgr.common.vision import TextDetection as Detection


@pytest.fixture(autouse=True)
def _stub_template_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """把模板加载换成命名空间与文件名组成的可比较哨兵。"""

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    monkeypatch.setattr(support_checker, 'load_ui_template', load_template)


def _detections(*texts: str, region: tuple[int, int, int, int] | None = None) -> list[Detection]:
    """按给定文案构造识别结果，可顺带带上同一块检测框。"""
    return [
        TextDetection(recognized_text=text, confidence_score=0.9, text_region=region)
        for text in texts
    ]


def _frame() -> numpy.ndarray:
    """构造一帧 1280x720 的黑图，只用来提供坐标换算所需的尺寸。"""
    return numpy.zeros((720, 1280, 3), dtype=numpy.uint8)


def test_button_center_uses_active_template_and_dead_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮落点只认已开启态模板，并限定在 1px 余量的窄区域里。"""
    calls: list[dict[str, object]] = []

    def expect_template_center(_ctx: object, **options: object) -> tuple[float, float]:
        calls.append(options)
        return (0.6617, 0.1653)

    monkeypatch.setattr(support_checker, 'expect_template_center', expect_template_center)

    assert read_tactical_support_button_center(object()) == (0.6617, 0.1653)
    assert calls[0]['template'] == (
        constants.TEMPLATE_NAMESPACE,
        constants.TACTICAL_SUPPORT_ACTIVE_TEMPLATE,
    )
    assert calls[0]['roi'] is constants.TACTICAL_SUPPORT_ROI
    assert calls[0]['attempts'] == 3
    assert calls[0]['interval_seconds'] == 0.5

    monkeypatch.setattr(support_checker, 'expect_template_center', lambda *_a, **_k: None)

    assert read_tactical_support_button_center(object()) is None


def test_popup_absent_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关文案读不到就当作浮窗没打开，不再解析其它字段。"""
    calls: list[dict[str, object]] = []

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=False, observation=[], screenshot=_frame())

    monkeypatch.setattr(support_checker, 'expect_ocr', expect_ocr)

    assert read_tactical_support(object()) is None
    assert calls[0]['roi'] == (
        constants.TACTICAL_SUPPORT_TOGGLE_ROI,
        constants.TACTICAL_SUPPORT_COUNT_ROI,
    )
    assert calls[0]['expect'] == ('未启用', '已启用')
    assert calls[0]['attempts'] == 5


@pytest.mark.parametrize(
    ('toggle_text', 'expected_enabled'),
    [('已启用', True), ('未启用', False)],
)
def test_read_tactical_support_reports_toggle_state(
    monkeypatch: pytest.MonkeyPatch,
    toggle_text: str,
    expected_enabled: bool,
) -> None:
    """开关文案决定是否已启用；次数区同时给出已用与总数。"""
    observation = [
        _detections(toggle_text, region=(10, 20, 60, 50)),
        _detections('本日剩余次数：3/10'),
    ]

    def expect_ocr(_ctx: object, **_options: object) -> SimpleNamespace:
        return SimpleNamespace(satisfied=True, observation=observation, screenshot=_frame())

    monkeypatch.setattr(support_checker, 'expect_ocr', expect_ocr)

    state = read_tactical_support(object())

    assert state is not None
    assert state.enabled is expected_enabled
    assert (state.remaining, state.total) == (3, 10)
    # 检测框相对识别区域，加上区域左上角偏移才是整帧位置。
    assert state.toggle_center == pytest.approx((950 / 1280, 363 / 720))


def test_read_tactical_support_tolerates_unreadable_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """次数区读不出数字时只丢次数，不影响开关状态。"""
    observation = [
        _detections('已启用'),
        _detections('本日剩余次数'),
    ]

    def expect_ocr(_ctx: object, **_options: object) -> SimpleNamespace:
        return SimpleNamespace(satisfied=True, observation=observation, screenshot=_frame())

    monkeypatch.setattr(support_checker, 'expect_ocr', expect_ocr)

    state = read_tactical_support(object())

    assert state is not None
    assert state.enabled is True
    assert (state.remaining, state.total) == (None, None)
    assert state.toggle_center is None
