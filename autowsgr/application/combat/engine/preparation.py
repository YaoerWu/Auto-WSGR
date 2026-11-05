"""模块功能：战斗的准备过渡段。

点下【开始出征】到第一个真实战斗阶段之间还有一段过场：出征动画、地图移动、
资源确认弹窗。这一段没有需要拍板的分支，只做两件事——点加速跳过过场、把
「船坞已满」这类开不了战的情况交回上层。

上层调用：
- application.combat.engine.loop：过场轮询时点加速。
- application.combat.engine.handlers：认出 `DOCK_FULL` 时记录并返回标记。

下层依赖：
- controller.sortie.battle_engine.page：点加速。
- application.combat.history：写入战斗事件。

边界：只管「刚点完出征」这一小段；战况、阵型、夜战这些要决策的不在这里，
也不判断打几场、打完去哪。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.combat.history import CombatEvent, EventType
from autowsgr.application.combat.types import ConditionFlag
from autowsgr.application.controller.sortie.battle_engine.page import click_speed_up
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.combat.history import CombatHistory
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


def accelerate(ctx: ContextHandle) -> None:
    """在出征过场里点一次加速。

    Args:
        ctx: 上下文句柄，提供设备点击。
    """
    click_speed_up(ctx)


def record_dock_full(history: CombatHistory, *, node: str) -> ConditionFlag:
    """记录「船坞已满」并返回结束标记。

    Args:
        history: 当前战斗的事件流。
        node: 当前所处节点名，用于事件记录。

    Returns:
        `ConditionFlag.DOCK_FULL`，由主循环转成战斗结果。
    """
    _log.warning('[COMBAT] 检测到船坞已满，战斗无法开始')
    history.add(
        CombatEvent(
            event_type=EventType.AUTO_RETURN,
            node=node,
            action='船坞已满',
        )
    )
    return ConditionFlag.DOCK_FULL


__all__ = ['accelerate', 'record_dock_full']
