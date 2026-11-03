"""模块功能：进入船池，把一个槽位换成目标舰船或清空。

上层调用：
- fleet_select.operation.member_align：把一个槽位换成目标舰船或清空。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.page：点槽位打开船池。
- application.controller.sortie.battle_preparation.ship_pool：船池页识别与单击操作。
- fleet_select.rules.ocr：把一屏列表文字定位成船卡。
- fleet_select.rules.constraints：判断一张船卡是否满足选船规则。
- fleet_select.rules.shipnames：搜索框里使用的舰名写法。
- fleet_select.types：选船规则。
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
from autowsgr.application.fleet_select.constants import (
    CARD_CLICK_SETTLE_SECONDS,
    LIST_SCAN_ATTEMPTS,
    POOL_OPEN_SETTLE_SECONDS,
    SCROLL_SETTLE_SECONDS,
    SEARCH_COMMIT_WAIT,
    SEARCH_KEYBOARD_WAIT,
    SEARCH_RESULT_WAIT,
)
from autowsgr.application.fleet_select.rules.constraints import get_card_verdict
from autowsgr.application.fleet_select.rules.ocr import (
    ShipCard,
    ShipListRow,
    recognize_ship_cards,
)
from autowsgr.application.fleet_select.rules.shipnames import get_active_ship_name_aliases
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.fleet_select.types import ShipSelector
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.operation.ship_select')


# ── 换船动作 ────────────────────────────────────────────────────────────────


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
        raise ValueError('至少需要提供一个选船配置')

    _open_ship_pool(ctx, slot)
    for index, option in enumerate(selectors):
        if index > 0 and use_search:
            # 上一条规则的搜索会让输入框留住文字并保持焦点，而键盘已经被回车收起；
            # 再点输入框不会重新唤起键盘。退出船池重新进入，拿到的是一张空的搜索框。
            _close_ship_pool(ctx)
            _open_ship_pool(ctx, slot)
        selected = _select_option_card(ctx, option, use_search=use_search)
        if selected is not None:
            return selected

    _close_ship_pool(ctx)
    _log.warning(
        '[FLEET] 船池 → 未找到候选，放弃本次选船：slot={}, expected={!r}',
        slot,
        [option.name for option in selectors],
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


# ── 船池定位 ────────────────────────────────────────────────────────────────


def _open_ship_pool(ctx: ContextHandle, slot: int) -> None:
    """点击准备页槽位并确认船池页面已经打开。

    Args:
        ctx: 提供设备服务的 dispatch 上下文句柄。
        slot: 需要打开的槽位序号，按画面从左到右 1 到 6。

    Raises:
        ActionFailedError: 点击槽位之后没有进入选船页。
    """
    FleetSlotPage(ctx).click_slot(slot)
    if not check_ship_pool_page(ctx):
        raise ActionFailedError('打开船池', f'第 {slot} 槽没有进入选船页')
    # 页面签名在滑入动画开始时就成立，此时点搜索框会被动画吞掉，
    # 等动画放完再操作。
    time.sleep(POOL_OPEN_SETTLE_SECONDS)


def _close_ship_pool(ctx: ContextHandle) -> None:
    """退出船池并确认已经回到准备页。

    Args:
        ctx: 提供设备服务的 dispatch 上下文句柄。

    Raises:
        ActionFailedError: 点了返回之后仍停在选船页。
    """
    if not check_ship_pool_page(ctx):
        return
    ShipPoolPage(ctx).go_back()
    if not check_ship_pool_page(ctx, absent=True):
        raise ActionFailedError('退出船池', '点了返回之后仍停在选船页')


def _select_option_card(
    ctx: ContextHandle,
    option: ShipSelector,
    *,
    use_search: bool,
) -> str | None:
    """在当前船池页面里执行一条规则：可选搜索、有限次扫列表、命中后点卡。"""
    page = ShipPoolPage(ctx)
    if use_search:
        _log.debug('[FLEET] 船池 → 打开搜索框：name={!r}', option.name)
        page.click_search_box()
        # 软键盘弹出有动画，键盘区域的白色键位要等动画结束才稳定下来。
        time.sleep(SEARCH_KEYBOARD_WAIT)
        if not check_search_input(ctx):
            raise ActionFailedError('打开搜索框', '软键盘没有出现')
        page.input_ship_name(_get_search_keyword(option))
        time.sleep(SEARCH_COMMIT_WAIT)
        # 回车既提交搜索也收起键盘；再点一次收起按钮会落到列表上，可能误点卡片。
        page.confirm_search()
        time.sleep(SEARCH_RESULT_WAIT)

    # 搜索生效后结果只占一屏，继续滚动会把过滤后的列表拖乱。
    scan_attempts = 1 if use_search else LIST_SCAN_ATTEMPTS
    for attempt in range(scan_attempts):
        card = _select_ship_card(ctx, option)
        if card is not None:
            time.sleep(CARD_CLICK_SETTLE_SECONDS)
            page.click_card_at(card.name.center)
            if not check_ship_pool_page(ctx, absent=True):
                raise ActionFailedError(
                    '选择舰船',
                    f'点了 {card.name.text!r} 之后没有离开选船页',
                )
            return card.name.text
        if attempt < scan_attempts - 1:
            page.scroll_list_down()
            time.sleep(SCROLL_SETTLE_SECONDS)
    return None


def _select_ship_card(ctx: ContextHandle, option: ShipSelector) -> ShipCard | None:
    """在当前可见列表里找出最满足规则的一张船卡。

    先在完全满足舰种与等级约束的卡片里取第一张；一张都没有时，退而取放宽约束
    后只差未知字段的卡片，未知字段越少越优先。
    """
    rows = [
        ShipListRow(text=item.text, center=item.center, region=item.region)
        for item in read_ship_list_texts(ctx)
    ]
    _log.debug(
        '[FLEET] 船池 → 扫列表：expected={!r}, rows={!r}',
        option.name,
        [(row.text, round(row.center[0], 4), round(row.center[1], 4)) for row in rows],
    )
    best_fallback: tuple[tuple[int, bool], int, ShipCard] | None = None
    for index, card in enumerate(recognize_ship_cards(rows, option.name)):
        verdict = get_card_verdict(option, card)
        if not verdict.accepted:
            continue
        if not verdict.is_fallback:
            return card
        sort_key = (*verdict.fallback_priority, index)
        if best_fallback is None or sort_key < best_fallback[0]:
            best_fallback = (sort_key, index, card)
    return best_fallback[2] if best_fallback is not None else None


def _get_search_keyword(option: ShipSelector) -> str:
    """把规则里的标准舰名换成游戏里实际显示的舰名。"""
    text = (option.search_name or option.name).strip()
    for display_name, system_name in get_active_ship_name_aliases().items():
        if system_name == text:
            return display_name
    return text


__all__ = ['remove_ship', 'select_ship']
