"""模块功能：验证出征准备页队伍选择控制器的点击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.battle_preparation.fleet_select。

边界：用替身接管设备点击，不访问设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.ui.controller.sortie.battle_preparation.fleet_select import (
    FLEET_TAB_CLICKS,
    SHIP_SLOT_CLICKS,
    FleetSelectPanel,
)


def _install_click_recorder() -> tuple[list[tuple[float, float]], SimpleNamespace]:
    """用替身接管设备点击，并记下每次点击的归一化坐标。"""
    clicks: list[tuple[float, float]] = []
    control = SimpleNamespace(click=lambda x, y: clicks.append((x, y)))
    ctx = SimpleNamespace(runtime=SimpleNamespace(ctrl=control))
    return clicks, ctx


@pytest.mark.parametrize('slot', [1, 2, 3, 4, 5, 6])
def test_click_ship_slot_uses_the_slot_calibration(slot: int) -> None:
    """六个槽位按画面从左到右的静态坐标点击立绘区中心。"""
    clicks, ctx = _install_click_recorder()

    FleetSelectPanel(ctx).click_ship_slot(slot)

    assert clicks == [SHIP_SLOT_CLICKS[slot]]


@pytest.mark.parametrize('fleet', [1, 2, 3, 4])
def test_click_fleet_tab_uses_the_fleet_calibration(fleet: int) -> None:
    """四个队伍页签按各自的静态坐标点击。"""
    clicks, ctx = _install_click_recorder()

    FleetSelectPanel(ctx).click_fleet_tab(fleet)

    assert clicks == [FLEET_TAB_CLICKS[fleet]]


@pytest.mark.parametrize('slot', [0, 7, -1])
def test_click_ship_slot_rejects_out_of_range_slot(slot: int) -> None:
    """越界槽位直接抛错，不点画面边缘。"""
    clicks, ctx = _install_click_recorder()

    with pytest.raises(ValueError, match='槽位编号必须是 1、2、3、4、5、6 之一'):
        FleetSelectPanel(ctx).click_ship_slot(slot)
    assert clicks == []


@pytest.mark.parametrize('fleet', [0, 5])
def test_click_fleet_tab_rejects_out_of_range_fleet(fleet: int) -> None:
    """越界队伍编号直接抛错。"""
    clicks, ctx = _install_click_recorder()

    with pytest.raises(ValueError, match='队伍编号必须是 1、2、3、4 之一'):
        FleetSelectPanel(ctx).click_fleet_tab(fleet)
    assert clicks == []
