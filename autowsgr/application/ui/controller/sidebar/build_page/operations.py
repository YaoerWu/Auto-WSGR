"""

操作层尚未迁移到新链路，当前不被任何模块导入；等第二阶段移植后恢复调用。模块功能：执行建造页面的标签切换和解体、建造原子点击操作。上层调用：
- application.ui.controller.sidebar.build_page.page：调用标签切换操作。
- application.ui.controller.sidebar.build_page.workflow：调用建造、收取和解装操作。

下层依赖：
- application.ui.controller.sidebar.build_page.constants：提供页面点击坐标。
- common.device：提供设备控制器契约。
- common.device.interaction：确认标签切换后的页面状态。

本模块只执行已确定目标的页面操作，不负责业务流程分支、业务结果判断或任务调度。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.sidebar.build_page import constants
from autowsgr.application.navigation.interaction import click_and_wait_for_page


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

    from autowsgr.common.device.service import DeviceService


def select_tab(
    ctrl: DeviceService,
    *,
    click_coord: tuple[float, float],
    checker: Callable[[np.ndarray], bool],
    source: str,
    target: str,
) -> None:
    """切换建造页面标签并确认目标标签到达。

    Args:
        ctrl: 当前设备控制器。
        click_coord: 目标标签点击坐标。
        checker: 已创建的目标标签页面检查器。
        source: 导航来源页面名称。
        target: 导航目标页面名称。

    Raises:
        NavigationError: 超时未到达目标标签。
    """
    click_and_wait_for_page(
        ctrl,
        click_coord=click_coord,
        checker=checker,
        source=source,
        target=target,
    )


def click_fast_build(ctrl: DeviceService, coordinate: tuple[float, float]) -> None:
    """点击识别到的快速建造按钮。"""
    ctrl.click(*coordinate)


def click_confirm_dialog(ctrl: DeviceService, coordinate: tuple[float, float]) -> None:
    """点击识别到的确认弹窗按钮。"""
    ctrl.click(*coordinate)


def click_dismiss_animation(ctrl: DeviceService) -> None:
    """点击建造结果动画的跳过区域。"""
    ctrl.click(*constants.CLICK_DISMISS_ANIMATION)


def click_start_build(ctrl: DeviceService, coordinate: tuple[float, float]) -> None:
    """点击识别到的新建造入口。"""
    ctrl.click(*coordinate)


def click_confirm_build(ctrl: DeviceService) -> None:
    """点击资源选择页面的建造确认按钮。"""
    ctrl.click(*constants.CLICK_CONFIRM)


def click_collect_slot(ctrl: DeviceService, coordinate: tuple[float, float]) -> None:
    """点击识别到的已完成建造槽位。"""
    ctrl.click(*coordinate)


def click_destroy_add(ctrl: DeviceService) -> None:
    """点击解体列表添加按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_ADD)


def click_destroy_type_filter(ctrl: DeviceService) -> None:
    """点击解体舰种过滤入口。"""
    ctrl.click(*constants.CLICK_DESTROY_TYPE_FILTER)


def click_destroy_type(ctrl: DeviceService, coordinate: tuple[float, float]) -> None:
    """点击指定舰种过滤坐标。"""
    ctrl.click(*coordinate)


def click_destroy_confirm_filter(ctrl: DeviceService) -> None:
    """点击舰种过滤确认按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_CONFIRM_FILTER)


def click_destroy_quick_select(ctrl: DeviceService) -> None:
    """点击解体快速选择按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_QUICK_SELECT)


def click_destroy_confirm_select(ctrl: DeviceService) -> None:
    """点击解体选择确认按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_CONFIRM_SELECT)


def click_destroy_remove_equipment(ctrl: DeviceService) -> None:
    """点击卸下装备选项。"""
    ctrl.click(*constants.CLICK_DESTROY_REMOVE_EQUIP)


def click_destroy_confirm(ctrl: DeviceService) -> None:
    """点击解体确认按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_CONFIRM)


def click_destroy_four_star(ctrl: DeviceService) -> None:
    """点击高星舰船解体确认按钮。"""
    ctrl.click(*constants.CLICK_DESTROY_FOUR_STAR_CONFIRM)


__all__ = [  # noqa: RUF022 - exports follow the page action order
    'select_tab',
    'click_fast_build',
    'click_confirm_dialog',
    'click_dismiss_animation',
    'click_start_build',
    'click_confirm_build',
    'click_collect_slot',
    'click_destroy_add',
    'click_destroy_type_filter',
    'click_destroy_type',
    'click_destroy_confirm_filter',
    'click_destroy_quick_select',
    'click_destroy_confirm_select',
    'click_destroy_remove_equipment',
    'click_destroy_confirm',
    'click_destroy_four_star',
]
