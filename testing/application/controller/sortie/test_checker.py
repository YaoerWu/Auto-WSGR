"""模块功能：验证出征页层识别的一次性探针契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.checker 与 vision 识别入口。

边界：用替身接管模板加载与识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller.sortie import checker as sortie_checker
from autowsgr.application.controller.sortie.checker import read_sortie_layer
from autowsgr.application.navigation.types import PageName


_LAYER_PAGES = tuple(page for page, _, _ in sortie_checker._LAYERS)
_LAYER_ROIS = tuple(roi for _, _, roi in sortie_checker._LAYERS)


def _install_recognition(
    monkeypatch: pytest.MonkeyPatch,
    active: tuple[int, ...],
) -> list[dict[str, object]]:
    """让指定序号的层命中，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        templates = options['template']
        observation = [
            SimpleNamespace(matched=index in active, score=0.95) for index in range(len(templates))
        ]
        return SimpleNamespace(satisfied=bool(active), observation=observation)

    monkeypatch.setattr(sortie_checker, 'load_ui_template', load_template)
    monkeypatch.setattr(sortie_checker, 'expect_template', expect_template)
    return calls


@pytest.mark.parametrize(
    ('active_index', 'expected'),
    [(index, (page,)) for index, page in enumerate(_LAYER_PAGES)],
)
def test_each_layer_probe_maps_to_its_page(
    monkeypatch: pytest.MonkeyPatch,
    active_index: int,
    expected: tuple[PageName, ...],
) -> None:
    """六层探针各自命中时分别映射到对应页面。"""
    _install_recognition(monkeypatch, (active_index,))

    assert read_sortie_layer(object()) == expected


def test_overlay_layer_wins_over_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    """浮窗标题与演习标签同时命中时按层顺序全部返回。"""
    _install_recognition(monkeypatch, (0, 2))

    assert read_sortie_layer(object()) == (
        PageName.EXERCISE_RIVAL_CONFIRM,
        PageName.EXERCISE,
    )


def test_no_layer_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    """一层都不命中时返回空元组。"""
    _install_recognition(monkeypatch, ())

    assert read_sortie_layer(object()) == ()


def test_probe_uses_single_call_with_all_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    """一次识别同时传全部层模板与识别区域，避免多次截图窗口。"""
    calls = _install_recognition(monkeypatch, (1,))

    read_sortie_layer(object(), attempts=2, interval_seconds=0.1)

    assert len(calls) == 1
    assert calls[0]['template'] == tuple(
        (sortie_checker.TEMPLATE_NAMESPACE, filename) for _, filename, _ in sortie_checker._LAYERS
    )
    assert calls[0]['roi'] == _LAYER_ROIS
    assert calls[0]['attempts'] == 2
    assert calls[0]['interval_seconds'] == 0.1
