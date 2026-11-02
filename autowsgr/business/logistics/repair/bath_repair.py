"""浴场泡澡修理 — 独立后勤链路。

链路契约 (主页锚点):
    主页面 → 后院 → 浴场 → 选择修理 (overlay) → ... → 回主页面。
    每个打断点 (无空槽 / 无候选 / 浴场满) 都直接返回, 游戏停在主页面。

Overlay 机制:
    "选择修理" 是浴场页面上的一个 overlay, 打开后仍识别为浴场页面,
    点击某艘舰船修理后 overlay 自动关闭。

调度关系:
    ``repair_one_available`` 由调度器周期产出 (TimerTrigger),
    在所有战斗任务完成后才执行 (空闲修船); 也可独立调用。

旧代码参考: ``game_operation.repair_by_bath``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.controller.backyard.bath import BathPage
from autowsgr.application.ui.navigation import goto_page
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import PageName, ShipDamageState


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.runtime import RuntimeContext as GameContext

_log = get_logger('business.logistics.repair')

# ═══════════════════════════════════════════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════════════════════════════════════════


def repair_manual_targets_in_bath(
    ctx: GameContext,
    ship_names: Sequence[str],
) -> list[str]:
    """按目标舰船名派发手动维修，并在结束后返回主页。"""
    from autowsgr.common.device.interaction import NavigationError

    bath = ctx.bathroom
    bath.slot_count = ctx.config.bathroom_count
    page = BathPage(ctx)
    targets = [name for name in ship_names if name]
    dispatched: list[str] = []

    try:
        if not targets:
            _log.debug(
                '[REPAIR] 手动维修 → 跳过：reason={!r}，result={!r}',
                'empty_targets',
                'not_started',
            )
            return dispatched

        for ship_name in targets:
            try:
                repair_seconds = page.repair(repair_all=False, ship_name=ship_name)
            except LookupError:
                _log.warning(
                    '[REPAIR] 手动维修 → 跳过舰船：ship_name={!r}，reason={!r}，result={!r}',
                    ship_name,
                    'not_in_repair_list',
                    'next_target',
                )
                continue
            except NavigationError as exc:
                _log.error(
                    '[REPAIR] 手动维修 → 终止：operation={!r}，error={!r}，result={!r}，next_action={!r}',
                    'repair_ship',
                    exc,
                    'failed',
                    'return_home',
                )
                break

            if repair_seconds < 0:
                _log.warning(
                    '[REPAIR] 手动维修 → 暂停：ship_name={!r}，reason={!r}，result={!r}',
                    ship_name,
                    'bath_full',
                    'not_repaired',
                )
                break

            ship = ctx.get_ship(ship_name)
            ship.set_repair(repair_seconds)
            ctx.update_ship_damage(ship_name, ShipDamageState.NORMAL)
            bath.occupy(repair_seconds)
            dispatched.append(ship_name)
            _log.info(
                '[REPAIR] 手动维修 → 派单成功：ship_name={!r}，repair_seconds={}，result={!r}',
                ship_name,
                repair_seconds,
                'success',
            )
    finally:
        try:
            goto_page(ctx, PageName.HOME)
        except Exception as exc:
            _log.warning(
                '[REPAIR] 手动维修 → 返回主页降级：reason={!r}，error={!r}，result={!r}，next_action={!r}',
                'navigation_failed',
                exc,
                'repair_state_preserved',
                'retry',
            )

    return dispatched


def repair_in_bath(ctx: GameContext) -> None:
    """使用浴室修理修理时间最长的舰船。

    流程: 导航到浴室 → 打开选择修理 overlay → 点击第一个待修理舰船
    (overlay 自动关闭)。

    旧代码参考: ``repair_by_bath(timer)``
    """
    goto_page(ctx, PageName.BATH)

    page = BathPage(ctx)
    page.repair(repair_all=True)

    # 点击全部修理后 overlay 已关闭，先回到浴室页面，再返回主界面
    time.sleep(1.0)
    try:
        goto_page(ctx, PageName.HOME)
    except Exception as exc:
        _log.warning(
            '[REPAIR] 全部修理 → 返回主页降级：reason={!r}，error={!r}，result={!r}，next_action={!r}',
            'navigation_failed',
            exc,
            'repair_finished',
            'retry',
        )
    _log.info('[REPAIR] 全部修理 → 完成：result={!r}', 'success')


def repair_ship_by_name(ctx: GameContext, ship_name: str) -> int:
    """使用浴室修理指定名称的舰船。

    Parameters
    ----------
    ctx:
        游戏上下文。
    ship_name:
        要修理的舰船名称 (中文)。

    Returns
    -------
    int
        修理时间 (秒)。若浴场已满则返回 ``-1``。
    """
    goto_page(ctx, PageName.BATH)

    page = BathPage(ctx)
    repair_secs = page.repair(repair_all=False, ship_name=ship_name)

    if repair_secs >= 0:
        ship = ctx.get_ship(ship_name)
        ship.set_repair(repair_secs)
        ctx.update_ship_damage(ship_name, ShipDamageState.NORMAL)
        _log.info(
            '[REPAIR] 指定修理 → 成功：ship_name={!r}，repair_seconds={}，result={!r}',
            ship_name,
            repair_secs,
            'success',
        )
    else:
        _log.warning(
            '[REPAIR] 指定修理 → 失败：ship_name={!r}，reason={!r}，result={!r}',
            ship_name,
            'bath_full',
            'not_repaired',
        )

    return repair_secs


def repair_one_available(
    ctx: GameContext,
    *,
    blacklist: list[str] | None = None,
) -> bool:
    """有空闲修理槽时, 派修直到填满所有空闲槽或无可修舰船 (调度入口)。

    由 ``auto_daily`` 调度器以 :class:`~autowsgr.dispatch.legacy_scheduler.triggers.TimerTrigger`
    周期产出, 经优先级队列在所有战斗任务 (战役/演习/常规战) 完成后才执行
    (空闲修船, 见 ``daily_plan.PRIO_BATH_REPAIR``)。流程:

    1. ``ctx.bathroom`` 无空闲槽 → 直接返回 (省一次开 overlay)。
    2. 导航浴室 → 循环 ``开选择修理 overlay → 修最长非黑名单船 → occupy 一个槽``,
       直到无空闲槽 / 无可修候选 / 浴场满。
       (游戏机制: 点击一艘船后 overlay 自动关闭, 故每修一艘需重开 overlay。)
    3. 派完后 ``ctx.bathroom.occupy`` 记录各槽释放时间, 返回主界面。

    Parameters
    ----------
    ctx:
        游戏上下文。
    blacklist:
        不修理的舰船名列表 (来自 ``daily_automation.bath_repair_blacklist``)。

    Returns
    -------
    bool
        ``True`` 至少派出一艘修理; ``False`` 无空位 / 无可修船 / 浴场满。
    """
    bath = ctx.bathroom
    bath.slot_count = ctx.config.bathroom_count
    if not bath.is_available():
        _log.debug(
            '[REPAIR] 浴室修理 → 跳过：reason={!r}，result={!r}',
            'no_available_slot',
            'not_started',
        )
        return False

    blocked = set(blacklist or [])
    goto_page(ctx, PageName.BATH)
    page = BathPage(ctx)
    repaired = 0

    # 循环填满所有空闲槽: 每修一艘 overlay 即自动关闭, 故每轮需重开 overlay。
    # 终止条件: 无空闲槽 (is_available False) / 无可修候选 (secs==-1) /
    # 浴场满 (secs==-2)。空闲槽数 = slot_count, 故循环上限即槽位数, 不会死循环。
    while bath.is_available():
        ship_name, secs = page.repair(repair_all=False, blacklist=blocked)

        if secs > 0:
            ship = ctx.get_ship(ship_name)
            ship.set_repair(secs)
            ctx.update_ship_damage(ship_name, ShipDamageState.NORMAL)
            bath.occupy(secs)
            repaired += 1
            _log.info(
                '[REPAIR] 浴室修理 → 派单成功：repair_seconds={}，dispatched={}，result={!r}',
                secs,
                repaired,
                'success',
            )
            continue
        if secs == -2:
            # 浴场满: 状态不可靠, 标记未知下次重试
            bath.mark_unknown()
            _log.warning(
                '[REPAIR] 浴室修理 → 暂停：reason={!r}，dispatched={}，next_action={!r}',
                'bath_full',
                repaired,
                'retry',
            )
            break
        # secs == -1 (无可修候选) 或 == 0 (修理时间解析失败): 状态不变, 结束派单
        _log.debug(
            '[REPAIR] 浴室修理 → 结束：reason={!r}，dispatched={}，result={!r}',
            'no_candidate',
            repaired,
            'not_repaired',
        )
        break

    time.sleep(1.0)
    try:
        goto_page(ctx, PageName.HOME)
    except Exception as exc:
        _log.warning(
            '[REPAIR] 浴室修理 → 返回主页降级：reason={!r}，error={!r}，result={!r}，next_action={!r}',
            'navigation_failed',
            exc,
            'repair_state_preserved',
            'retry',
        )
    return repaired > 0
