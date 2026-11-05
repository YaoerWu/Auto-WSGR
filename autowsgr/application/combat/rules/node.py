"""模块功能：节点推进的血量判定。

上层调用：
- application.combat.engine.decision：节点前进对话框按舰队血量决定走还是回港。

边界：只回答「这队血还能不能继续走」；不认画面、不点按钮。
"""

from __future__ import annotations

from autowsgr.application.combat.types import RepairMode, ShipDamageState


def check_blood(
    ship_stats: list[ShipDamageState],
    proceed_stop: RepairMode | list[RepairMode],
) -> bool:
    """判断当前舰队血量是否满足继续前进的条件。

    Args:
        ship_stats: 六个槽位的血量状态。
        proceed_stop: 每槽位的停手档位，单个档位会对六个槽位生效。

    Returns:
        还能继续前进返回真。
    """
    thresholds = [proceed_stop] * 6 if isinstance(proceed_stop, RepairMode) else proceed_stop
    return all(
        state == ShipDamageState.NO_SHIP or state < thresholds[index]
        for index, state in enumerate(ship_stats[: len(thresholds)])
    )


__all__ = ['check_blood']
