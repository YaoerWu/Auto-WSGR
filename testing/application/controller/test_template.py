"""模块功能：验证 UI 模板加载入口的路径拼接与缓存。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.template。

边界：用替身接管底层 load_template，不读取模板图片。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller import template as template_module
from autowsgr.application.controller.template import load_ui_template


@pytest.fixture(autouse=True)
def _clear_template_cache() -> None:
    """每个用例前后清空进程级模板缓存，避免用例互相看到对方的替身。"""
    load_ui_template.cache_clear()
    yield
    load_ui_template.cache_clear()


def _capture_load(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """用替身接管底层加载入口并记录路径与模板名。"""
    calls: list[tuple[str, str | None]] = []

    def fake_load(path: str, *, name: str | None = None) -> object:
        calls.append((path, name))
        return SimpleNamespace(path=path, name=name)

    monkeypatch.setattr(template_module, 'load_template', fake_load)
    return calls


def test_builds_path_under_application_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """模板路径统一落在 application 根下，模板名默认取文件名主干。"""
    calls = _capture_load(monkeypatch)

    load_ui_template('controller/home', 'HOME_MAIN_720P.png')

    assert calls == [('application/controller/home/HOME_MAIN_720P.png', 'HOME_MAIN_720P')]


def test_accepts_explicit_template_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """调用方可以指定模板名，路径仍按命名空间与文件名拼接。"""
    calls = _capture_load(monkeypatch)

    load_ui_template('controller/login', 'SERVER_SWITCH_ENTRY_720P.png', name='switch_entry')

    assert calls == [
        ('application/controller/login/SERVER_SWITCH_ENTRY_720P.png', 'switch_entry'),
    ]


def test_reuses_loaded_template_for_same_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一命名空间与文件名只加载一次，后续调用命中的是缓存。"""
    calls = _capture_load(monkeypatch)

    first = load_ui_template('controller/mission', 'MISSION_ALL_TAB_720P.png')
    second = load_ui_template('controller/mission', 'MISSION_ALL_TAB_720P.png')

    assert first is second
    assert len(calls) == 1
