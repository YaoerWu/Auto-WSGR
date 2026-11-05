"""战役业务执行器。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from autowsgr.application.combat import run_battle
from autowsgr.application.combat.types import ConditionFlag
from autowsgr.application.navigation import goto_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.runtime.executor import BaseExecutor
from autowsgr.business.combat import CombatResult
from autowsgr.common.system.logger import get_logger

from .operations import CampaignOperations
from .spec import CAMPAIGN_DAILY_LIMIT, CampaignSpec


if TYPE_CHECKING:
    from autowsgr.application.runtime import RuntimeContext as GameContext

_log = get_logger('business.combat.campaign')


class CampaignExecutor(BaseExecutor):
    """执行一次战役；重复次数由 Processor 的 count 控制。"""

    # ── 初始化 ─────────────────────────────────────────────────

    def __init__(self, ctx: GameContext, params: dict | None = None, **kwargs: Any) -> None:
        super().__init__(ctx, params, **kwargs)
        self.spec = CampaignSpec.from_params(self.params)
        self._operations = CampaignOperations(
            self.ctx,
            wait=self._wait,
            report=self._report,
            save_progress=self._save_fleet_progress,
        )

    # ── 主流程 ─────────────────────────────────────────────────

    def _execute(self) -> CombatResult:
        # 重置任务进度上下文
        previous = self.progress.get('_result')
        if previous is not None and not isinstance(previous, CombatResult):
            raise TypeError('任务进度 _result 必须是 CombatResult')

        # 2、读取连续战役的页面复用标记。
        reuse_page = self.progress.pop('_reuse_campaign_page', False)
        if not isinstance(reuse_page, bool):
            raise TypeError('任务进度 _reuse_campaign_page 必须是布尔值')

        try:
            # 3、暂停恢复已有结果时直接交回处理器。
            if previous is not None:
                self.progress.pop('_result', None)
                self.progress.pop('_campaign_fleet', None)
                return previous

            # 6、检查每日战役次数。
            executed = self._campaign_count()
            if executed >= CAMPAIGN_DAILY_LIMIT:
                result = CombatResult(flag=ConditionFlag.BATTLE_TIMES_EXCEED)
                self._report('stop_after_current', reason=result.flag.value)
                return result

            # 7、记录任务并在非连续场景导航到战役入口。
            _log.info(
                '[Campaign] 开始战役任务：{}（{}）',
                self.spec.campaign_name,
                self.spec.difficulty,
            )
            if not reuse_page:
                goto_page(self.ctx, PageName.SORTIE_MAP)
            self._operations.enter_campaign(self.spec)

            # 8、等待出征准备页稳定后加载战役编队。
            self._wait(0.5)
            page, ship_stats, fleet = self._operations.prepare_battle(
                self.spec,
                reset_fleet=not self._has_fleet_checkpoint(),
            )

            # 9、编队完成后检查出征前断点。
            self._report('before_start')
            self._wait(0.2)

            # 10、点击出征；次数耗尽时结束当前任务。
            if not self._operations.start_battle(page):
                result = CombatResult(
                    flag=ConditionFlag.BATTLE_TIMES_EXCEED,
                    ship_stats=ship_stats,
                    fleet=fleet,
                )
                self._report('stop_after_current', reason=result.flag.value)
                return result

            # 11、等待页面离开准备态后开始战役战斗。
            time.sleep(1.0)
            _log.info(
                '[Campaign] 进入战斗：阵型配置={}，夜战配置={}',
                self.spec.plan.default_node.formation.name,
                self.spec.plan.default_node.night,
            )
            result = run_battle(
                self.ctx,
                self.spec.plan,
                ship_stats=ship_stats,
                stop_requested=self._stop.is_set,
            )

            # 12、把本次编队写入战斗结果。
            result.fleet = fleet
            if result.flag is ConditionFlag.OPERATION_SUCCESS:
                # 13、保存战果和次数，供暂停或连续任务恢复。
                executed += 1
                self.progress['_campaign_completed'] = executed
                self.progress['_result'] = result
                _log.info(
                    '[Campaign] 战斗结束，战役结果：{}，已执行战役次数 {}，剩余次数 {}',
                    result.flag.value,
                    executed,
                    max(CAMPAIGN_DAILY_LIMIT - executed, 0),
                )
                self._report(
                    'battle_done',
                    executed=executed,
                    remaining=max(CAMPAIGN_DAILY_LIMIT - executed, 0),
                )
                self._wait(0.2)
                self.progress.pop('_result', None)
                self.progress.pop('_campaign_fleet', None)
                return result

            # 14、次数耗尽或船坞已满时交回处理器收口。
            if result.flag in {ConditionFlag.BATTLE_TIMES_EXCEED, ConditionFlag.DOCK_FULL}:
                self._report('stop_after_current', reason=result.flag.value)
                return result
            raise RuntimeError(f'战役战斗未成功: {result.flag.value}')
        finally:
            # 15、异常或停止后回到首页；连续战役保留当前页面。
            try:
                if not reuse_page and not self.progress.get('_reuse_campaign_page', False):
                    goto_page(self.ctx, PageName.HOME)
            except Exception as error:
                _log.error('[Campaign] 返回首页失败: {}', error)

    # ── 进度与断点 ─────────────────────────────────────────────

    def _save_fleet_progress(self, data: dict[str, Any]) -> None:
        # 保存当前编队阶段，暂停恢复时跳过已完成的清空动作。
        self.progress['_campaign_fleet'] = dict(data)

    def _has_fleet_checkpoint(self) -> bool:
        # 校验编队断点，避免用损坏进度继续操作设备。
        checkpoint = self.progress.get('_campaign_fleet')
        if checkpoint is None:
            return False
        if not isinstance(checkpoint, dict):
            raise TypeError('任务进度 _campaign_fleet 必须是对象')
        if checkpoint.get('stage') not in {'cleared', 'selected', 'complete'}:
            raise ValueError('任务进度 _campaign_fleet.stage 无效')
        return True

    def _campaign_count(self) -> int:
        # 读取已完成次数，限制在合法的非负整数范围。
        value = self.progress.get('_campaign_completed', 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TypeError('任务进度 _campaign_completed 必须是非负整数')
        return value
