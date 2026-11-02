"""模块功能：验证建造页面入口、标签切换和两个业务流程的边界。

上层调用：
- pytest：执行本模块的页面治理回归。

下层依赖：
- application.ui.controller.sidebar.build_page：提供页面入口、操作和流程实现。
- common.types：提供解装流程使用的舰种枚举。

本模块只使用设备和视觉替身验证页面边界，不连接真实设备或改写业务配置。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from autowsgr.application.controller.sidebar.build import (
    BuildPage,
    BuildTab,
)
from autowsgr.application.ui.controller.sidebar.build_page import operations as operations_module
from autowsgr.application.ui.controller.sidebar.build_page import page as page_module
from autowsgr.application.ui.controller.sidebar.build_page import workflow as workflow_module
from autowsgr.common.types import ShipType


def _page() -> tuple[BuildPage, MagicMock]:
    ctrl = MagicMock()
    return BuildPage(SimpleNamespace(ctrl=ctrl)), ctrl


def test_select_tab_uses_target_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    checker = object()
    calls: list[dict[str, object]] = []

    def capture(actual_ctrl: object, **kwargs: object) -> None:
        calls.append({'ctrl': actual_ctrl, **kwargs})

    monkeypatch.setattr(operations_module, 'click_and_wait_for_page', capture)

    operations_module.select_tab(
        ctrl,
        click_coord=(0.2, 0.3),
        checker=checker,
        source='建造',
        target='建造-开发',
    )

    assert calls == [
        {
            'ctrl': ctrl,
            'click_coord': (0.2, 0.3),
            'checker': checker,
            'source': '建造',
            'target': '建造-开发',
        }
    ]


def test_build_selects_tab_before_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    page, ctrl = _page()
    checker = object()
    calls: list[tuple[str, object, dict[str, object]]] = []

    def select_tab(actual_ctrl: object, **kwargs: object) -> None:
        calls.append(('tab', actual_ctrl, kwargs))

    def build(actual_ctrl: object, **kwargs: object) -> int:
        calls.append(('workflow', actual_ctrl, kwargs))
        return 2

    monkeypatch.setattr(page_module.operations, 'select_tab', select_tab)
    monkeypatch.setattr(page_module.workflow, 'build', build)
    monkeypatch.setattr(page_module, 'create_tab_checker', lambda *_args: checker)

    assert page.build(build_count=0, collect_completed=False) == 2
    assert calls == [
        (
            'tab',
            ctrl,
            {
                'click_coord': page_module.constants.TAB_POSITIONS['build'],
                'checker': checker,
                'source': page_module.PageName.BUILD,
                'target': f'{page_module.PageName.BUILD}-{BuildTab.BUILD.value}',
            },
        ),
        (
            'workflow',
            ctrl,
            {
                'build_count': 0,
                'collect_completed': False,
                'build_type': 'ship',
                'allow_fast_build': False,
            },
        ),
    ]


def test_build_collects_before_starting_new_build(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    collected_detail = SimpleNamespace(center=(0.2, 0.3))
    start_detail = SimpleNamespace(center=(0.4, 0.5))
    matches = iter([collected_detail, None, start_detail, start_detail])
    template_states = iter([False, False, True, True])
    calls: list[str] = []

    monkeypatch.setattr(workflow_module.ImageChecker, 'find_template', lambda *_args: next(matches))
    monkeypatch.setattr(
        workflow_module.ImageChecker,
        'template_exists',
        lambda *_args: next(template_states),
    )
    monkeypatch.setattr(workflow_module.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(workflow_module.time, 'monotonic', lambda: 0.0)
    for name in ('click_collect_slot', 'click_start_build', 'click_confirm_build'):
        monkeypatch.setattr(
            workflow_module.operations,
            name,
            lambda *_args, _name=name: calls.append(_name),
        )

    assert workflow_module.build(ctrl, build_count=2) == 1
    assert calls == [
        'click_collect_slot',
        'click_start_build',
        'click_confirm_build',
        'click_start_build',
        'click_confirm_build',
    ]


def test_build_rejects_full_depot_before_click(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    detail = SimpleNamespace(center=(0.2, 0.3))
    monkeypatch.setattr(workflow_module.ImageChecker, 'find_template', lambda *_args: detail)
    monkeypatch.setattr(workflow_module.ImageChecker, 'template_exists', lambda *_args: True)

    with pytest.raises(RuntimeError, match='仓库已满'):
        workflow_module.build(ctrl, build_count=0)

    ctrl.click.assert_not_called()


def test_destroy_ships_preserves_operation_order(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = MagicMock()
    calls: list[str] = []
    operation_names = [
        'click_destroy_add',
        'click_destroy_type_filter',
        'click_destroy_type',
        'click_destroy_confirm_filter',
        'click_destroy_quick_select',
        'click_destroy_confirm_select',
        'click_destroy_confirm',
        'click_destroy_four_star',
    ]
    for name in operation_names:
        monkeypatch.setattr(
            workflow_module.operations,
            name,
            lambda *_args, _name=name: calls.append(_name),
        )
    monkeypatch.setattr(workflow_module.time, 'sleep', lambda _seconds: None)

    workflow_module.destroy_ships(
        ctrl,
        ship_types=[ShipType.DD],
        remove_equipment=False,
    )

    assert calls == operation_names


def test_page_destroy_selects_tab_before_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    page, ctrl = _page()
    checker = object()
    calls: list[tuple[str, object, dict[str, object]]] = []

    def select_tab(actual_ctrl: object, **kwargs: object) -> None:
        calls.append(('tab', actual_ctrl, kwargs))

    def destroy(actual_ctrl: object, **kwargs: object) -> None:
        calls.append(('workflow', actual_ctrl, kwargs))

    monkeypatch.setattr(page_module.operations, 'select_tab', select_tab)
    monkeypatch.setattr(page_module.workflow, 'destroy_ships', destroy)
    monkeypatch.setattr(page_module, 'create_tab_checker', lambda *_args: checker)

    page.destroy_ships([ShipType.DD], remove_equipment=False)

    assert calls == [
        (
            'tab',
            ctrl,
            {
                'click_coord': page_module.constants.TAB_POSITIONS['destroy'],
                'checker': checker,
                'source': page_module.PageName.BUILD,
                'target': f'{page_module.PageName.BUILD}-{BuildTab.DESTROY.value}',
            },
        ),
        (
            'workflow',
            ctrl,
            {
                'ship_types': [ShipType.DD],
                'remove_equipment': False,
            },
        ),
    ]
