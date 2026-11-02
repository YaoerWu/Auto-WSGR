"""模块功能：编排编队选船节点的搜索、船卡选择、移除和返回流程。

上层调用：
- formation.fleet_adjustment：传入物理槽位和有序舰船规则。

下层依赖：
- ship_selection.page：执行船池页面原子 UI 动作。
- ship_selection.recognition：识别可见船卡和约束结果。
- ship_selection.constants：提供等待、滚动和重试参数。
- common.device.interaction：确认船池页面已经离开。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.ship_selection import constants, recognition
from autowsgr.application.ui.controller.fleet.formation.ship_selection.page import (
    ShipSelectionPage,
)
from autowsgr.application.navigation.interaction import wait_for_page, wait_leave_page
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.ui.controller.context import UIContext
    from autowsgr.application.ui.controller.fleet.main_page import BattlePreparationPage
    from autowsgr.business.combat.fleet_models import ShipSelector


_log = get_logger('ui.fleet.formation.ship_selection')


def select_ship(
    ctx: UIContext,
    page: BattlePreparationPage,
    slot: int,
    selectors: Sequence[ShipSelector],
    *,
    use_search: bool = True,
) -> str | None:
    """在指定准备页槽位按有序规则选择一艘舰船。

    Args:
        ctx: 当前运行上下文，提供设备和 OCR 引擎。
        page: 当前出征准备页控制器。
        slot: 需要更换的物理槽位，范围为 0 到 5。
        selectors: 已由编队调整节点排序的主选和备选规则。
        use_search: 是否使用船池搜索框。

    Returns:
        实际选择到的舰船名称；所有规则均未命中时返回 None。
    """
    if not selectors:
        raise ValueError('selectors 不能为空')
    if ctx.ocr is None:
        raise RuntimeError('编队选船需要 OCR 引擎')

    selection_page = _open_selection_page(ctx, page, slot)
    for selector in selectors:
        selected = _select_one_selector(
            ctx,
            selection_page,
            selector,
            use_search=use_search,
        )
        if selected is not None:
            return selected

    selection_page.go_back(page.check_current_page)
    _log.error('[Fleet] 未在选船列表中找到满足规则的候选: {}', [item.name for item in selectors])
    return None


def remove_ship(
    ctx: UIContext,
    page: BattlePreparationPage,
    slot: int,
) -> None:
    """打开指定槽位的船池页面并移除当前舰船。"""
    selection_page = _open_selection_page(ctx, page, slot)
    selection_page.click_remove_ship()
    wait_leave_page(
        ctx.ctrl,
        ShipSelectionPage.check_current_page,
        timeout=constants.CHOOSE_PAGE_TIMEOUT,
        source='编队选船',
        target='编队',
    )


def _open_selection_page(
    ctx: UIContext,
    page: BattlePreparationPage,
    slot: int,
) -> ShipSelectionPage:
    """点击准备页槽位并等待船池页面出现。"""
    page.click_ship_slot(slot)
    wait_for_page(
        ctx.ctrl,
        ShipSelectionPage.check_current_page,
        timeout=constants.CHOOSE_PAGE_TIMEOUT,
        source='编队',
        target='编队选船',
    )
    return ShipSelectionPage(ctx)


def _select_one_selector(
    ctx: UIContext,
    selection_page: ShipSelectionPage,
    selector: ShipSelector,
    *,
    use_search: bool,
) -> str | None:
    """在当前船池页面中执行一条规则的有限识别和滚动。"""
    if use_search:
        selection_page.open_search_box()
        selection_page.input_ship_name(
            recognition._normalize_search_keyword(selector.search_name or selector.name),
        )
        selection_page.dismiss_keyboard()

    for attempt in range(constants.OCR_MAX_ATTEMPTS):
        screen = ctx.ctrl.screenshot()
        selected, retry_level_ocr = recognition._find_ship_card(
            ctx.ocr,
            screen,
            selector.name,
            ship_types=selector.ship_types or None,
            min_level=selector.min_level,
            max_level=selector.max_level,
            relaxed_constraints=selector.relaxed_constraints,
        )
        if selected is not None:
            matched, center_x, center_y = selected
            time.sleep(constants.CARD_CLICK_WAIT)
            selection_page.click_ship_card(center_x, center_y)
            wait_leave_page(
                ctx.ctrl,
                ShipSelectionPage.check_current_page,
                timeout=constants.CHOOSE_PAGE_TIMEOUT,
                source='编队选船',
                target='编队',
            )
            return matched
        if retry_level_ocr and not selector.relaxed_constraints:
            if attempt < constants.OCR_MAX_ATTEMPTS - 1:
                time.sleep(constants.LEVEL_RETRY_WAIT)
                continue
            return None
        if attempt < constants.OCR_MAX_ATTEMPTS - 1:
            selection_page.scroll_list()
            time.sleep(constants.SCROLL_WAIT)
    return None


__all__ = ['remove_ship', 'select_ship']
