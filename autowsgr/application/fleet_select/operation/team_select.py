"""模块功能：识别并点击准备页上的 1 到 4 队队伍标签。

上层调用：
- fleet_select.models.normal：换船前先切到目标舰队。

下层依赖：
- application.controller.sortie.battle_preparation：读当前队标签、点目标队标签。
- fleet_select.constants：切换后等待时间。

边界：只负责读队标签与点队标签这一件事，不判断编成、不读舰船、不决定换船策略。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation import (
    BattlePreparationPage,
    read_team_tab,
)
from autowsgr.application.errors import ActionFailedError
from autowsgr.application.fleet_select.constants import FLEET_SWITCH_WAIT
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.operation.team_select')

# 舰队标签页的合法编号。
_FLEET_IDS = frozenset({1, 2, 3, 4})


def select_team(ctx: ContextHandle, fleet_id: int | None) -> None:
    """切到目标舰队；当前已经是这一支时不重复点击。

    Args:
        ctx: 提供设备服务的 dispatch 上下文句柄。
        fleet_id: 目标舰队编号 1 到 4；为空表示沿用当前舰队。

    Raises:
        ValueError: 舰队编号越界。
        ActionFailedError: 点完标签后复核仍不是目标舰队。
    """
    if fleet_id is None:
        return
    if fleet_id not in _FLEET_IDS:
        raise ValueError(f'舰队编号必须在 1 到 4 之间，实际为 {fleet_id}')
    if read_team_tab(ctx) == fleet_id:
        return

    BattlePreparationPage(ctx).click_team_tab(fleet_id)
    time.sleep(FLEET_SWITCH_WAIT)
    switched = read_team_tab(ctx)
    if switched != fleet_id:
        raise ActionFailedError('切换舰队', f'点了第 {fleet_id} 队之后读到的是第 {switched} 队')
    _log.info('[FLEET] 编队 → 切换队伍：舰队编号={}', fleet_id)


__all__ = ['select_team']
