"""模块功能：验证舰队槽位点击与拖拽入口的落点与越界校验。

直接调用方：项目测试运行器。

直接依赖：pytest、ship_recognition.page、ship_recognition.constants 与控制器测试 conftest 的离屏上下文。

边界：只记录点击与滑动参数，不连设备、不读模板文件。
"""

from __future__ import annotations

import pytest

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.constants import (
    CLICK_SHIP_SLOTS,
    DRAG_DURATION_SECONDS,
    FLEET_SLOT_COUNT,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    FleetSlotPage,
)


def test_click_slot_clicks_each_slot_center(ctx: object, control: object) -> None:
    """六个槽位按序号点击各自卡片中心。"""
    page = FleetSlotPage(ctx)

    for slot in range(1, FLEET_SLOT_COUNT + 1):
        page.click_slot(slot)

    assert control.clicks == list(CLICK_SHIP_SLOTS)
    assert len(CLICK_SHIP_SLOTS) == FLEET_SLOT_COUNT

    xs = [int(x * 1280) for x, _y in CLICK_SHIP_SLOTS]
    assert xs == sorted(xs)
    assert all(0.0 < y < 0.6 for _x, y in CLICK_SHIP_SLOTS)


@pytest.mark.parametrize('slot', [0, 7, -1])
def test_click_slot_rejects_out_of_range(ctx: object, control: object, slot: int) -> None:
    """槽位序号越界时直接报错，且不产生任何点击。"""
    page = FleetSlotPage(ctx)

    with pytest.raises(ValueError, match='槽位序号必须在 1 到 6 之间'):
        page.click_slot(slot)

    assert control.clicks == []


def test_drag_slot_swipes_from_source_to_target(ctx: object, control: object) -> None:
    """拖拽按源槽位到目标槽位的落点滑动，时长取公开常量。"""
    page = FleetSlotPage(ctx)

    page.drag_slot(2, 5)

    assert control.swipes == [(*CLICK_SHIP_SLOTS[1], *CLICK_SHIP_SLOTS[4], DRAG_DURATION_SECONDS)]


@pytest.mark.parametrize(('source', 'target'), [(0, 1), (1, 7), (-1, 3)])
def test_drag_slot_rejects_out_of_range(
    ctx: object,
    control: object,
    source: int,
    target: int,
) -> None:
    """任一端槽位越界时直接报错，且不产生滑动。"""
    page = FleetSlotPage(ctx)

    with pytest.raises(ValueError, match='槽位序号必须在 1 到 6 之间'):
        page.drag_slot(source, target)

    assert control.swipes == []
