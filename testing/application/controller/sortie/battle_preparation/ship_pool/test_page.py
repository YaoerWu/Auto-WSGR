"""模块功能：验证船池页面单击控制器的坐标契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.battle_preparation.ship_pool.page 与共用离屏上下文。

边界：用共用离屏上下文记录点击与滑动，不识别画面、不访问设备。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_pool import (
    page as ship_pool_page,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool.page import ShipPoolPage


if TYPE_CHECKING:
    from typing import Any


def test_page_actions_use_calibrated_positions(ctx: Any, control: Any) -> None:
    """搜索、收键盘、移除、返回都点在校准落点上。"""
    page = ShipPoolPage(ctx)
    page.click_search_box()
    page.dismiss_keyboard()
    page.click_remove_ship()
    page.go_back()

    assert control.clicks == [
        ship_pool_page.CLICK_SEARCH_BOX,
        ship_pool_page.CLICK_DISMISS_KEYBOARD,
        ship_pool_page.CLICK_REMOVE_SHIP,
        ship_pool_page.CLICK_BACK,
    ]


def test_input_ship_name_writes_text(ctx: Any, control: Any) -> None:
    """输入舰名走设备文字输入，不产生点击。"""
    page = ShipPoolPage(ctx)
    page.input_ship_name('企业')

    assert control.texts == ['企业']
    assert control.clicks == []


def test_click_card_uses_recognition_center(ctx: Any, control: Any) -> None:
    """点卡直接使用识别出的归一化中心。"""
    page = ShipPoolPage(ctx)
    page.click_card_at((0.31, 0.42))

    assert control.clicks == [(0.31, 0.42)]


def test_scroll_list_uses_calibrated_swipe(ctx: Any, control: Any) -> None:
    """列表滚动使用固定起止点与时长。"""
    page = ShipPoolPage(ctx)
    page.scroll_list_down()

    assert control.swipes == [
        (
            *ship_pool_page.SCROLL_START,
            *ship_pool_page.SCROLL_END,
            ship_pool_page.SCROLL_DURATION_SECONDS,
        ),
    ]
