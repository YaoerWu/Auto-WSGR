"""演习准备页导航节点的无设备回归。"""

from autowsgr.application.navigation.graph import find_path
from autowsgr.application.navigation.registry import get_registered_pages, register_default_pages
from autowsgr.common.types import PageName


def test_battle_preparation_has_no_generic_map_parent_edge() -> None:
    """出征准备页的父页面依赖战斗模式，不注册无来源区分的通用边。"""
    register_default_pages()
    assert PageName.BATTLE_PREPARATION.value in get_registered_pages()

    path = find_path(PageName.BATTLE_PREPARATION.value, PageName.HOME.value)

    assert path is None
