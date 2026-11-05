"""战役旧入口兼容壳。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.combat.types import ConditionFlag, Formation
from autowsgr.application.controller.types import RepairMode
from autowsgr.business.combat.campaign.executor import CampaignExecutor
from autowsgr.business.combat.campaign.spec import (
    CAMPAIGN_NAME_MAP,
    CAMPAIGN_NAMES,
    parse_campaign_name,
)


if TYPE_CHECKING:
    from autowsgr.application.combat.history import CombatResult
    from autowsgr.application.runtime import RuntimeContext as GameContext


class CampaignRunner:
    """兼容旧 ``CampaignRunner`` 调用方式，实际执行委托给新执行器。"""

    def __init__(
        self,
        ctx: GameContext,
        campaign_name: str,
        times: int = 3,
        formation: Formation = Formation.double_column,
        night: bool = True,
        repair_mode: RepairMode = RepairMode.moderate_damage,
    ) -> None:
        if isinstance(times, bool) or not isinstance(times, int) or times < 1:
            raise ValueError('times 必须是正整数')
        parse_campaign_name(campaign_name)
        self._ctx = ctx
        self._campaign_name = campaign_name
        self._times = times
        self._formation = formation
        self._night = night
        self._repair_mode = repair_mode

    def run(self) -> list[CombatResult]:
        """执行旧接口请求指定的战役次数。"""
        params = {
            'campaign_name': self._campaign_name,
            'formation': self._formation.value,
            'night': self._night,
            'repair_mode': self._repair_mode.value,
        }
        stop = getattr(self._ctx, 'stop_event', None)
        results: list[CombatResult] = []
        for _ in range(self._times):
            if stop is not None and stop.is_set():
                break
            result = CampaignExecutor(self._ctx, params, stop=stop).run()
            results.append(result)
            if result.flag in {ConditionFlag.BATTLE_TIMES_EXCEED, ConditionFlag.DOCK_FULL}:
                break
        return results


__all__ = [
    'CAMPAIGN_NAMES',
    'CAMPAIGN_NAME_MAP',
    'CampaignRunner',
    'parse_campaign_name',
]
