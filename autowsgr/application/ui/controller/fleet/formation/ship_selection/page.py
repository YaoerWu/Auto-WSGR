"""模块功能：执行船池页面的检查、搜索输入、点击和返回操作。

上层调用：
- ship_selection.workflow：编排单舰搜索、选择、移除和页面退出。
- application.navigation.registry：注册船池页面检查器。

下层依赖：
- ship_selection.constants：提供船池页面和滚动坐标。
- common.device.interaction、common.vision：提供页面终态等待和页面模板匹配。

本文件只执行船池页面 UI 动作，不读取船卡 OCR，不解析选择规则。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.ship_selection import constants
from autowsgr.application.navigation.interaction import (
    click_and_wait_for_page,
    wait_for_page,
    wait_leave_page,
)
from autowsgr.application.navigation.types import PageMatch, PageName
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import PixelChecker


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy

    from autowsgr.application.ui.controller.context import UIContext
    from autowsgr.common.device.service import DeviceService


_log = get_logger('ui.fleet.formation.ship_selection')


class ShipSelectionPage:
    """船池选择页面控制器，只提供页面级 UI 操作。"""

    def __init__(self, ctx: UIContext) -> None:
        """保存调用方注入的上下文和设备控制器。"""
        self._ctx = ctx
        self._ctrl: DeviceService = ctx.ctrl

    @staticmethod
    def check_current_page(screen: numpy.ndarray) -> PageMatch:
        """判断截图是否为船池选择页面。"""
        result = PixelChecker.check_signature(screen, constants.PAGE_SIGNATURE)
        return PageMatch(
            name=PageName.SHIP_SELECTION.value,
            matched=result.matched,
            score=result.ratio,
        )

    def open_search_box(self) -> None:
        """打开船池搜索框并确认输入控件出现。"""
        _log.debug('[UI] 编队选船 -> 打开搜索框')
        self._ctrl.click(*constants.CLICK_SEARCH_BOX)
        wait_for_page(
            self._ctrl,
            lambda screen: (
                PixelChecker.check_signature(
                    screen,
                    constants.INPUT_SIGNATURE,
                ).matched
            ),
            timeout=constants.CHOOSE_PAGE_TIMEOUT,
            source=PageName.SHIP_SELECTION,
            target='船池输入',
        )

    def input_ship_name(self, name: str) -> None:
        """向船池搜索框输入舰船名称。"""
        _log.debug("[UI] 编队选船 -> 输入舰船名 '{}'", name)
        self._ctrl.text(name)

    def dismiss_keyboard(self) -> None:
        """关闭软键盘并确认搜索输入控件消失。"""
        _log.debug('[UI] 编队选船 -> 关闭键盘')
        self._ctrl.click(*constants.CLICK_DISMISS_KEYBOARD)
        wait_leave_page(
            self._ctrl,
            lambda screen: (
                PixelChecker.check_signature(
                    screen,
                    constants.INPUT_SIGNATURE,
                ).matched
            ),
            timeout=constants.CHOOSE_PAGE_TIMEOUT,
            source='船池输入',
            target=PageName.SHIP_SELECTION,
        )

    def click_ship_card(self, x: float, y: float) -> None:
        """点击识别到的船卡中心。"""
        self._ctrl.click(x, y)

    def click_remove_ship(self) -> None:
        """点击移除按钮，清空准备页当前舰船槽位。"""
        _log.debug('[UI] 编队选船 -> 移除舰船')
        self._ctrl.click(*constants.CLICK_REMOVE_SHIP)

    def scroll_list(self) -> None:
        """向上滚动船池列表，查找当前页面未显示的船卡。"""
        self._ctrl.swipe(
            constants.SCROLL_X,
            constants.SCROLL_FROM_Y,
            constants.SCROLL_X,
            constants.SCROLL_TO_Y,
            duration=constants.SCROLL_DURATION,
        )

    def go_back(self, parent_checker: Callable[[numpy.ndarray], PageMatch]) -> None:
        """退出船池页面并确认返回调用方页面。

        Args:
            parent_checker: 调用方页面的页面状态检查器，用于确认船池页面已退出。
        """
        _log.debug('[UI] 编队选船 -> 返回编队')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=constants.CLICK_BACK,
            checker=parent_checker,
            source=PageName.SHIP_SELECTION,
            target=PageName.BATTLE_PREPARATIONARATION,
        )


__all__ = ['ShipSelectionPage']
