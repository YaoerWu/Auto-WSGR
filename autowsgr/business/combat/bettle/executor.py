"""普通出征和活动出征的统一任务入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.navigation import goto_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.runtime.executor import BaseExecutor
from autowsgr.business.combat import CombatPlan, CombatResult
from autowsgr.business.combat.bettle.normal_fight import NormalFightRunner
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.runtime import RuntimeContext as GameContext


_log = get_logger('business.combat.bettle')
_BETTLE_TASK_TYPES = frozenset({'normal_fight', 'event_fight'})


class BettleExecutor(BaseExecutor):
    """按 task_type 选择普通或活动导航并执行一次出击。"""

    # ── 初始化 ─────────────────────────────────────────────────

    def __init__(self, ctx: GameContext, params: dict | None = None, **kwargs: Any) -> None:
        super().__init__(ctx, params, **kwargs)
        declared_type = self.params.pop('task_type', None)
        task_type = self.task_type or declared_type or 'normal_fight'
        if task_type not in _BETTLE_TASK_TYPES:
            raise ValueError(f'不支持的 bettle task_type: {task_type}')
        if declared_type is not None and declared_type != task_type:
            raise ValueError('Bettle YAML 的 task_type 与处理器类型不一致')
        self.task_type = task_type
        self.plan = CombatPlan.from_dict(self.params)

    # ── 主流程 ─────────────────────────────────────────────────

    def _execute(self) -> CombatResult:
        """执行一场出击并回到主页；启动与恢复由 dispatch 处理器负责。"""
        _log.info('[Bettle] 开始{}任务', '活动战' if self.task_type == 'event_fight' else '普通战')
        try:
            result = NormalFightRunner(
                self.ctx,
                self.plan,
                task_type=self.task_type,
                wait=self._wait,
                repair_status_callback=lambda repairing: self._report(
                    'repairing',
                    repairing=repairing,
                ),
            ).run()
            self._report('battle_done', task_type=self.task_type, result=result.flag.value)
            return result
        finally:
            if not self._pause.is_set() and not self._stop.is_set():
                try:
                    goto_page(self.ctx, PageName.HOME)
                except Exception as error:
                    _log.error('[Bettle] 返回首页失败: {}', error)


__all__ = ['BettleExecutor']
