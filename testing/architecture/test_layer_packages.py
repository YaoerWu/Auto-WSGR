"""Regression checks for the five-package architecture boundary."""

from __future__ import annotations

import ast
from pathlib import Path


_ROOT = Path(__file__).parents[2] / 'autowsgr'
_LAYERS = ('server', 'dispatch', 'business', 'application', 'common')
_RANK = {name: index for index, name in enumerate(_LAYERS)}


def test_application_and_common_packages_import_without_side_effects() -> None:
    import autowsgr.application
    import autowsgr.common

    assert autowsgr.application.__doc__
    assert autowsgr.common.__doc__


def test_autowsgr_has_only_the_five_architecture_packages() -> None:
    packages = {
        item.name for item in _ROOT.iterdir() if item.is_dir() and item.name != '__pycache__'
    }

    assert packages == set(_LAYERS)


def test_business_has_only_combat_and_logistics_domains() -> None:
    domains = {
        item.name
        for item in (_ROOT / 'business').iterdir()
        if item.is_dir() and item.name != '__pycache__'
    }

    assert domains == {'combat', 'logistics'}


def test_ui_legacy_compatibility_layer_is_removed() -> None:
    """页面实现只能从 canonical UI 包加载。"""
    assert not (_ROOT / 'application' / 'ui' / 'legacy').exists()


def test_ui_pages_are_replaced_by_controller() -> None:
    """页面 Controller 和共享页面能力使用唯一的新归属。"""
    ui = _ROOT / 'application' / 'ui'
    assert (ui / 'controller').is_dir()
    assert (ui / 'controller' / 'shared').is_dir()
    assert not (ui / 'pages').exists()
    assert (_ROOT / 'common' / 'vision' / 'blood.py').is_file()
    assert (_ROOT / 'common' / 'vision' / 'map.py').is_file()
    assert not (ui / 'controller' / 'battle_preparation' / 'blood.py').exists()
    assert not (ui / 'controller' / 'battle_preparation' / 'constants.py').exists()


def test_shared_tabbed_templates_resolve_from_controller_path() -> None:
    """迁移后的标签页识别仍然从 common 资源目录加载模板。"""
    from autowsgr.common.calibration.tabbed import TEMPLATE_DIR

    assert TEMPLATE_DIR == _ROOT / 'common' / 'data' / 'images' / 'ui'
    assert TEMPLATE_DIR.is_dir()


def test_navigation_service_only_owns_navigation_flow() -> None:
    """页面识别不应重新回到 service.py。"""
    navigation = _ROOT / 'application' / 'ui' / 'navigation'
    service = ast.parse((navigation / 'service.py').read_text(encoding='utf-8'))
    functions = [node.name for node in service.body if isinstance(node, ast.FunctionDef)]

    assert functions == ['goto_page', '_goto_page']
    assert (navigation / 'recognition.py').is_file()


def test_navigation_graph_is_split_by_domain() -> None:
    """导航边按公共、战斗、后勤域保存。"""
    graph = _ROOT / 'application' / 'ui' / 'navigation' / 'graph'

    assert (graph / 'common.py').is_file()
    assert (graph / 'combat.py').is_file()
    assert (graph / 'logistics.py').is_file()

    from autowsgr.application.navigation.graph import (
        COMBAT_EDGES,
        COMMON_EDGES,
        LOGISTICS_EDGES,
        NAV_GRAPH,
    )

    assert (len(COMMON_EDGES), len(COMBAT_EDGES), len(LOGISTICS_EDGES)) == (5, 5, 13)
    assert len(NAV_GRAPH) == 23


def test_navigation_support_has_one_owner_per_responsibility() -> None:
    """注册表不承载识别，页面栈不承载设备识别。"""
    from autowsgr.application.navigation import recognition, registry
    from autowsgr.application.navigation.stack import UIStack

    assert hasattr(recognition, 'get_current_page')
    assert not hasattr(registry, 'get_current_page')
    assert not hasattr(UIStack, 'resync')


def test_combat_shared_fleet_rules_are_flat_files() -> None:
    combat = _ROOT / 'business' / 'combat'

    assert (combat / 'fleet.py').is_file()
    assert not (combat / 'fleet').exists()
    assert (_ROOT / 'business' / 'fleet_policy.py').is_file()


def test_runtime_and_combat_support_stay_below_business() -> None:
    assert (_ROOT / 'application' / 'runtime' / 'executor.py').is_file()
    assert not (_ROOT / 'business' / 'base.py').exists()
    assert (_ROOT / 'application' / 'combat' / 'history.py').is_file()
    assert not (_ROOT / 'business' / 'combat' / 'history.py').exists()
    assert (_ROOT / 'application' / 'combat' / 'engine' / 'phase_handlers.py').is_file()


def test_combat_handlers_and_runner_have_single_owners() -> None:
    combat = _ROOT / 'business' / 'combat'
    handlers = combat / 'handlers'

    assert (handlers / '__init__.py').is_file()
    assert (handlers / 'decision.py').is_file()
    assert (handlers / 'settlement.py').is_file()
    assert not (combat / 'handlers.py').exists()
    assert (combat / 'runner.py').is_file()
    assert not (combat / 'engine.py').exists()


def test_layer_imports_only_point_downward() -> None:
    violations: list[str] = []

    for path in _ROOT.rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        owner = path.relative_to(_ROOT).parts[0]
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        imported_layers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            else:
                continue
            for name in names:
                parts = name.split('.')
                if len(parts) > 1 and parts[0] == 'autowsgr' and parts[1] in _RANK:
                    imported_layers.add(parts[1])
        violations.extend(
            f'{path}: {owner} -> {target}'
            for target in imported_layers
            if _RANK[target] < _RANK[owner]
        )

    assert violations == []
