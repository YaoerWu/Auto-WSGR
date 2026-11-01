"""模块功能：验证出征页域探针的判层契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.sortie 与 vision 识别入口。

边界：用替身接管识别入口，不加载模板图片、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.ui.navigation.checker.sortie import checker as sortie_checker
from autowsgr.application.ui.navigation.checker.sortie import read_sortie_layer
from autowsgr.application.ui.navigation.types import PageName


_LAYERS = sortie_checker._LAYERS
_PAGES = tuple(page for page, *_ in _LAYERS)


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    *,
    active: tuple[int, ...] = (),
) -> list:
    """用替身接管识别入口：只有指定位置的模板算命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        templates = options['template']
        observation = [
            SimpleNamespace(matched=(index in active)) for index in range(len(templates))
        ]
        return SimpleNamespace(satisfied=bool(active), observation=observation)

    monkeypatch.setattr(sortie_checker, 'expect_template', expect_template)
    return calls


@pytest.mark.parametrize(('active_index', 'expected'), tuple(enumerate(_PAGES)))
def test_report_single_layer(
    monkeypatch: pytest.MonkeyPatch,
    active_index: int,
    expected: PageName,
) -> None:
    """只有一层命中时，返回只含该层的元组。"""
    _install_recognition(monkeypatch, active=(active_index,))

    assert read_sortie_layer(object()) == (expected,)


def test_report_no_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """一层都没命中时返回空元组。"""
    _install_recognition(monkeypatch)

    assert read_sortie_layer(object()) == ()


def test_report_overlay_above_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗不遮挡标签栏时两层一起返回，浮窗在前——它才是当前最上层。"""
    overlay_index = _PAGES.index(PageName.EXERCISE_RIVAL_CONFIRM)
    exercise_index = _PAGES.index(PageName.EXERCISE)
    _install_recognition(monkeypatch, active=(overlay_index, exercise_index))

    assert read_sortie_layer(object()) == (
        PageName.EXERCISE_RIVAL_CONFIRM,
        PageName.EXERCISE,
    )


def test_read_all_layers_in_one_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """整个域共用一次截图：一次调用传齐模板与区域。"""
    calls = _install_recognition(monkeypatch, active=(1,))

    read_sortie_layer(object())

    assert len(calls) == 1
    assert len(calls[0]['template']) == len(_LAYERS)
    assert len(calls[0]['roi']) == len(_LAYERS)
