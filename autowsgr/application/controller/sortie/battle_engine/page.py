"""模块功能：战斗内的物理点击动作。

上层调用：
- application.combat.engine：阶段推进时按当前阶段调用。

下层依赖：
- controller.sortie.battle_engine.constants：点击坐标与固定等待时间。
- common.device：通过 ContextHandle 里的设备服务下发点击。
- common.vision：按模板中心点击，以及资源确认弹窗探测。

边界：只做点击和固定等待；不识别页面语义、不做决策、不记录战斗历史。
"""

from __future__ import annotations

import time
from functools import cache
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_engine.constants import (
    CLICK_ENTER_FIGHT,
    CLICK_NIGHT_NO,
    CLICK_NIGHT_YES,
    CLICK_PROCEED_NO,
    CLICK_PROCEED_YES,
    CLICK_RESULT_CONTINUE,
    CLICK_RETREAT,
    CLICK_SETTLE_SECONDS,
    CLICK_SPEED_UP_BATTLE,
    CLICK_SPEED_UP_NORMAL,
    CONFIRM_CLOSE_SECONDS,
    CONFIRM_SETTLE_SECONDS,
    CONFIRM_TEMPLATE,
    ENTER_FIGHT_SETTLE_SECONDS,
    FORMATION_SETTLE_SECONDS,
    SPEED_UP_SETTLE_SECONDS,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import adapters, expect_template_center
from autowsgr.common.vision.adapters.template_matching import load_template


if TYPE_CHECKING:
    import numpy

    from autowsgr.application.combat.types import FightCondition, Formation
    from autowsgr.common.vision import Template
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


# ══════════════════════════════════════════════════════════════════════════════
# 点击动作
# ══════════════════════════════════════════════════════════════════════════════


def click_retreat(ctx: ContextHandle) -> None:
    """点击索敌成功界面的撤退按钮。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
    """
    ctx.runtime.ctrl.click(*CLICK_RETREAT)
    time.sleep(CLICK_SETTLE_SECONDS)


def click_enter_fight(ctx: ContextHandle) -> None:
    """点击索敌成功界面的进入战斗按钮。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
    """
    time.sleep(ENTER_FIGHT_SETTLE_SECONDS)
    ctx.runtime.ctrl.click(*CLICK_ENTER_FIGHT)
    time.sleep(CLICK_SETTLE_SECONDS)


def click_formation(ctx: ContextHandle, formation: Formation) -> None:
    """选择阵型。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        formation: 目标阵型。
    """
    _log.debug('[COMBAT] 选择阵型：{} ({})', formation.name, formation.value)
    ctx.runtime.ctrl.click(*formation.relative_position)
    time.sleep(FORMATION_SETTLE_SECONDS)


def click_fight_condition(ctx: ContextHandle, condition: FightCondition) -> None:
    """选择战况。

    选择战况后舰队会立即在地图上移动，因此这里不能加随机延迟，否则会识别
    不到下一个节点。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        condition: 目标战况。
    """
    ctx.runtime.ctrl.click(*condition.relative_click_position, delay=False)


def click_night_battle(ctx: ContextHandle, *, pursue: bool) -> None:
    """选择夜战或撤退。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        pursue: 真为追击进入夜战，假为撤退。
    """
    _log.debug('[COMBAT] 夜战选择：{}', '追击' if pursue else '撤退')
    ctx.runtime.ctrl.click(*(CLICK_NIGHT_YES if pursue else CLICK_NIGHT_NO))


def click_proceed(ctx: ContextHandle, *, go_forward: bool) -> None:
    """选择继续前进或返回港口。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        go_forward: 真为前进，假为回港。
    """
    _log.debug('[COMBAT] 继续前进：{}', '前进' if go_forward else '回港')
    ctx.runtime.ctrl.click(*(CLICK_PROCEED_YES if go_forward else CLICK_PROCEED_NO))


def click_result(ctx: ContextHandle) -> None:
    """点击战果类页面的继续按钮。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
    """
    ctx.runtime.ctrl.click(*CLICK_RESULT_CONTINUE)


def click_speed_up(ctx: ContextHandle, *, battle_mode: bool = False) -> None:
    """点击地图移动或战斗中的加速按钮。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        battle_mode: 真为战役加速坐标，假为常规战加速坐标。
    """
    coords = CLICK_SPEED_UP_BATTLE if battle_mode else CLICK_SPEED_UP_NORMAL
    time.sleep(SPEED_UP_SETTLE_SECONDS)
    ctx.runtime.ctrl.click(*coords, delay=False)


def click_skip_missile_animation(ctx: ContextHandle) -> None:
    """跳过导弹支援动画。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
    """
    ctx.runtime.ctrl.click(*CLICK_SPEED_UP_BATTLE, delay=False)


def click_template(
    ctx: ContextHandle,
    template: Template,
    *,
    attempts: int = 7,
    interval_seconds: float = 0.3,
) -> bool:
    """等待模板出现并点击它的中心。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        template: 待点击的模板。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        命中并点击返回真，识别窗口耗尽返回假。
    """
    center = expect_template_center(
        ctx,
        template=template,
        confidence=0.8,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if center is None:
        return False
    ctx.runtime.ctrl.click(*center)
    return True


def dismiss_resource_confirm(ctx: ContextHandle, frame: numpy.ndarray) -> None:
    """发现资源确认弹窗时点掉它并重新加速。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        frame: 当前帧，避免轮询里为了一次探测重复截图。
    """
    result = adapters.match_template(
        frame,
        _load_template(CONFIRM_TEMPLATE),
        confidence=0.75,
    )
    if not result.matched or result.center is None:
        return
    time.sleep(CONFIRM_SETTLE_SECONDS)
    ctx.runtime.ctrl.click(*result.center, delay=False)
    _log.info('[COMBAT] 点掉资源确认弹窗：{}', result.center)
    time.sleep(CONFIRM_CLOSE_SECONDS)
    ctx.runtime.ctrl.click(*CLICK_SPEED_UP_BATTLE, delay=False)


# ══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ══════════════════════════════════════════════════════════════════════════════


@cache
def _load_template(relative_path: str) -> Template:
    """加载战斗模板；同一路径只读盘一次。"""
    return load_template(relative_path)


__all__ = [
    'click_enter_fight',
    'click_fight_condition',
    'click_formation',
    'click_night_battle',
    'click_proceed',
    'click_result',
    'click_retreat',
    'click_skip_missile_animation',
    'click_speed_up',
    'click_template',
    'dismiss_resource_confirm',
]
