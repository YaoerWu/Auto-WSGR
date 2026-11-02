"""模块功能：编排船池里的单槽换船与清空。

上层调用：
- application.fleet_select.battle_preparation：三套换船编排都靠它把一个槽位换成目标舰船。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.page：点槽位打开船池。
- application.controller.sortie.battle_preparation.ship_pool：船池页识别与单击操作。
- application.fleet_select.models：选船规则。
- application.fleet_select.names：舰名归一化与别名。
- application.errors：换船失败时抛出具体操作错误。

边界：只编排「打开船池 → 搜索 → 找到目标 → 点卡 → 确认离开」这一段，
不判断整队阵容是否合格、不决定换哪些槽位、不做全局槽位分配。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_pool import (
    ShipPoolPage,
    check_search_input,
    check_ship_pool_page,
    read_ship_list_texts,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    FleetSlotPage,
)
from autowsgr.application.errors import ActionFailedError
from autowsgr.application.fleet_select.names import (
    get_active_ship_name_aliases,
    ship_name_identity,
)
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.controller.sortie.battle_preparation.ship_pool import ShipListText
    from autowsgr.application.fleet_select.models import ShipSelector
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.ship_pool')


# ── 校准 ────────────────────────────────────────────────────────────────────

# 每条规则最多扫几屏船池列表；三屏之后还没找到就换下一条备选。
_LIST_SCAN_ATTEMPTS = 3

# 滚动之后给列表回弹留的时间，避免截到模糊的过场帧。
_SCROLL_SETTLE_SECONDS = 0.5

# 点卡前给卡片选中动画留的时间，否则点击可能落在动画中途。
_CARD_CLICK_SETTLE_SECONDS = 1.0


# ── 编排入口 ────────────────────────────────────────────────────────────────


def select_ship(
    ctx: ContextHandle,
    *,
    slot: int,
    selectors: Sequence[ShipSelector],
    use_search: bool = True,
) -> str | None:
    """在指定准备页槽位按有序规则选择一艘舰船。

    Args:
        ctx: 提供设备服务的 dispatch 上下文句柄。
        slot: 需要更换的槽位序号，按画面从左到右 1 到 6。
        selectors: 已排好序的主选与备选规则，前一条找不到才试下一条。
        use_search: 是否使用船池搜索框；决战页没有搜索框，必须传 False。

    Returns:
        实际选中的舰名原文；所有规则都没有找到时返回 None。

    Raises:
        ValueError: 规则列表为空。
        ActionFailedError: 船池没有打开，或点卡之后没有离开船池页。
    """
    if not selectors:
        raise ValueError('selectors 不能为空')

    _open_ship_pool(ctx, slot)
    for selector in selectors:
        selected = _select_one_selector(ctx, selector, use_search=use_search)
        if selected is not None:
            return selected

    ShipPoolPage(ctx).go_back()
    _log.error(
        '[换船] 第 {} 槽没有找到满足规则的候选: {}',
        slot,
        [selector.name for selector in selectors],
    )
    return None


def remove_ship(ctx: ContextHandle, *, slot: int) -> None:
    """打开指定槽位的船池页面并移除当前舰船。

    Args:
        ctx: 提供设备服务的 dispatch 上下文句柄。
        slot: 需要清空的槽位序号，按画面从左到右 1 到 6。

    Raises:
        ActionFailedError: 船池没有打开，或移除之后没有离开船池页。
    """
    _open_ship_pool(ctx, slot)
    ShipPoolPage(ctx).click_remove_ship()
    if not check_ship_pool_page(ctx, absent=True):
        raise ActionFailedError('移除舰船', f'第 {slot} 槽移除后没有离开选船页')


# ── 私有步骤 ────────────────────────────────────────────────────────────────


def _open_ship_pool(ctx: ContextHandle, slot: int) -> None:
    """点击准备页槽位并确认船池页面已经打开。"""
    FleetSlotPage(ctx).click_slot(slot)
    if not check_ship_pool_page(ctx):
        raise ActionFailedError('打开船池', f'第 {slot} 槽没有进入选船页')


def _select_one_selector(
    ctx: ContextHandle,
    selector: ShipSelector,
    *,
    use_search: bool,
) -> str | None:
    """在当前船池页面里执行一条规则：可选搜索、有限次扫列表、命中后点卡。"""
    page = ShipPoolPage(ctx)
    if use_search:
        page.click_search_box()
        if not check_search_input(ctx):
            raise ActionFailedError('打开搜索框', '软键盘没有出现')
        page.input_ship_name(_search_keyword(selector))
        page.dismiss_keyboard()

    for attempt in range(_LIST_SCAN_ATTEMPTS):
        hit = _find_ship_card(ctx, selector)
        if hit is not None:
            time.sleep(_CARD_CLICK_SETTLE_SECONDS)
            page.click_card_at(hit.center)
            if not check_ship_pool_page(ctx, absent=True):
                raise ActionFailedError('选择舰船', f'点了 {hit.text!r} 之后没有离开选船页')
            return hit.text
        if attempt < _LIST_SCAN_ATTEMPTS - 1:
            page.scroll_list_down()
            time.sleep(_SCROLL_SETTLE_SECONDS)
    return None


def _find_ship_card(ctx: ContextHandle, selector: ShipSelector) -> ShipListText | None:
    """在当前可见列表文字里找第一条属于目标舰名的记录。"""
    for item in read_ship_list_texts(ctx):
        if _matches_ship_name(selector.name, item.text):
            return item
    return None


def _search_keyword(selector: ShipSelector) -> str:
    """把规则里的舰名换成搜索框认得的写法。"""
    text = (selector.search_name or selector.name).strip()
    return get_active_ship_name_aliases().get(text, text)


def _matches_ship_name(target: str, text: str) -> bool:
    """比较目标舰名与列表上的 OCR 原文，不修改任何一方。"""
    identity = ship_name_identity(target)
    return identity is not None and identity == ship_name_identity(text)


__all__ = ['remove_ship', 'select_ship']
