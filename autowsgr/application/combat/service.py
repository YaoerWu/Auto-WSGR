"""模块功能：战斗引擎的唯一对外入口。

一场战斗从点下【开始出征】开始，到战果页退出、回到出发页结束。调用方只提供
战斗计划与开战前的舰船状态，剩下的识别、点击、走位、结算全在内部完成，中途
不向外抛断点。

上层调用：
- business.combat 各模式：传入已构造好的战斗计划。

下层依赖：
- application.combat.engine.loop：主循环。

边界：不负责进图选章、编队换船、补给修理，也不决定打几场、打完去哪。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.combat.engine.loop import CombatLoop
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.application.combat.history import CombatResult
    from autowsgr.application.combat.types import BattlePlan, ShipDamageState
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


def run_battle(
    ctx: ContextHandle,
    plan: BattlePlan,
    *,
    ship_stats: list[ShipDamageState],
    stop_requested: Callable[[], bool] | None = None,
) -> CombatResult:
    """跑完一整场战斗。

    Args:
        ctx: 任务上下文，提供设备与配置。
        plan: 战斗计划，含模式、地图、节点决策与转移表。
        ship_stats: 开战前六艘船的损伤状态。
        stop_requested: 外部停止询问函数，返回真时主循环尽快退出。

    Returns:
        战果汇总，含每场战斗明细、结束时舰船状态与掉落统计。
    """
    _log.info(
        '[COMBAT] 战斗开始：模式={!r} 章节={!r} 地图={!r}',
        plan.mode,
        plan.chapter,
        plan.map_id,
    )
    result = CombatLoop(ctx, stop_requested=stop_requested).run(plan, ship_stats)
    _log.info(
        '[COMBAT] 战斗结束：退出原因={!r} 节点数={} 掉落={}',
        result.flag,
        result.node_count,
        result.loot_count,
    )
    return result


__all__ = ['run_battle']
