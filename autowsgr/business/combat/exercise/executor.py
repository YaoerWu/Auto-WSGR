"""演习执行器 — 以单场挑战为基本执行单元 (2026-08 定稿)。

执行模式 ：由 rivals_limit 参数区分
1、完整模式 (默认, rivals_limit=None):
    - 重复次数由请求的 count 字段控制, 不写入 YAML。
2、限额模式 (rivals_limit=N):
    - 累计挑战 N 个对手后即视为完成; N=1 为单场模式。

执行逻辑：
1、以单场为计数单位, _fight_one() 每完成一场挑战后，progress['fought'] 累加一次
2、任务被暂停后重跑时计数延续，不因重新调度而清零或重复统计。
3、插队执行逻辑：
    - 执行器在断点检测到暂停信号
    - 返回主页让出控制权，等待处理器调度高优先级任务结束
    - 本任务重新调度, 依据对手挑战状态识别(已挑战对手呈现置灰) 跳过已完成场次
    - 继续处理剩余对手, 直至无可挑战对手后正常结束。

行为逻辑：
1、主页 → goto_page(MAP) → 切换演习面板
2、识别对手状态 → 选择对手 → 二次确认弹窗
3、出征准备页 (选择编队 + 船损检测) → 出征
4、run_combat(EXERCISE) → 结算 → 返回演习面板 → 下一对手
4、执行结束，返回主页

可插队节点：暂停检查内置于 _wait, 处理器置位信号后在最近断点生效:
1、面板导航完成后 (panel_ready 之后的等待点)
2、对手确认后 (rival_confirmed 之后的等待点, 已进入准备页)
3、编队完成后 (fleet_ready 之后的等待点, 尚未出征, 状态可完全回退)
4、每场战斗完成后 (rival_done 之后的等待点, 强制检查, 含最后一场)
5、位于出征准备页；该页已注册为导航节点，暂停时由导航回到地图页再回主页。

"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from autowsgr.application.combat import run_battle
from autowsgr.application.combat.types import ConditionFlag
from autowsgr.application.navigation import goto_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.runtime.executor import BaseExecutor
from autowsgr.business.combat.exercise.spec import ExerciseSpec
from autowsgr.business.combat.fleet import exact_fleet_rules
from autowsgr.common.system.logger import get_logger

from .operations import ExerciseOperations


if TYPE_CHECKING:
    from autowsgr.application.controller.types import ShipDamageState
    from autowsgr.application.runtime import RuntimeContext as GameContext
    from autowsgr.business.combat import CombatResult


_log = get_logger('business.combat.exercise')


class ExerciseExecutor(BaseExecutor):
    """演习执行器: 单场挑战为基本执行单元, 按模式迭代至终止条件。"""

    # ── 初始化 ─────────────────────────────────────────────────

    def __init__(self, ctx: GameContext, params: dict | None = None, **kwargs: Any) -> None:
        super().__init__(ctx, params, **kwargs)
        self.spec = ExerciseSpec.from_params(self.params)
        self.plan = self.spec.plan
        self.fleet_selection = self.spec.fleet_selection
        self.fleet_id = self.fleet_selection.fleet_id
        self.rivals_limit = self.spec.rivals_limit
        """单轮挑战数量上限 (None=完整模式不限; N=限额模式, 1 为单次)。"""
        self.rival = self.spec.rival
        """指定对手编号; ``None`` 表示自动选择。"""
        self._operations = ExerciseOperations(
            self.ctx,
            wait=self._wait,
            report=self._report,
        )

    # ── 主流程 ─────────────────────────────────────────────────

    def _execute(self) -> list[CombatResult]:
        # 重置任务进度上下文
        previous = self.progress.get('_results', [])

        if not isinstance(previous, list):
            raise TypeError('任务进度 _results 必须是列表')
        results: list[CombatResult] = list(previous)

        try:
            _log.info(
                '[Exercise] 演习编队加载：队伍 {}，规则 {}',
                self.fleet_id,
                '已配置'
                if self.fleet_selection.slot_rules or self.fleet_selection.plain_fleet
                else '沿用当前队伍',
            )

            # 1、导航到演习入口
            goto_page(self.ctx, PageName.SORTIE_MAP)
            self._operations.switch_to_exercise_panel()
            self._wait(1.0)  # 断点①：面板导航完成后

            # 判断任务终止条件: 完整模式 — 无可挑战对手; 限额模式 — 配额耗尽。
            while self._has_quota():
                target = self._operations.pick_rival(self.rival)
                if target is None:
                    break  # 无可挑战对手, 本轮结束

                # 2、执行一次演习
                results.append(self._fight_one(target))

                # 3、识别演习战果，并存入变量
                self.progress['_results'] = results
                self._wait(1.0)  # 断点④：战斗完成后 (强制检查, 含最后一场)
                if not self._has_quota():
                    break  # 配额耗尽, 无需复位面板

                # 4、回到演习入口
                goto_page(self.ctx, PageName.SORTIE_MAP)
                self._operations.switch_to_exercise_panel()  # 复位面板, 供下一场识别

            _log.info(
                '[Exercise] 演习完成，本次 {} 场，累计计数 {}',
                len(results),
                self.progress.get('fought', 0),
            )

            # 4、演习结果存入上下文
            self.progress.pop('_results', None)
            return results
        finally:
            # 任务异常、停止或暂停都不能把设备留在演习链路中；清理错误
            # 只记录，不覆盖原始业务异常。
            try:
                goto_page(self.ctx, PageName.HOME)
            except Exception as error:
                _log.error('[Exercise] 返回首页失败: {}', error)

    # ── 基本执行单元: 单场挑战 ─────────────────────────────────

    def _fight_one(self, target: int) -> CombatResult:
        """执行单场挑战: 选择对手 → 编队 → 出征 → 战斗, 完成后计数累加。"""

        # 1、识别战斗对手
        self._operations.select_rival(target)

        # 2、点击确认按钮，进入出征准备页
        self._operations.enter_battle()
        self._report('rival_confirmed', rival=target)
        self._wait(1.0)  # 断点②：对手确认后 (已进入准备页)

        # 3、把 YAML 舰队转换成槽位规则。
        slot_rules = self.fleet_selection.slot_rules
        if slot_rules is None and self.fleet_selection.plain_fleet is not None:
            slot_rules = exact_fleet_rules(self.fleet_selection.plain_fleet)

        # 4、进入编队流程，按照 YAML 完成编队
        # 断点④：每一次换完船，都可以识别断点并且插入优先级更高的队伍
        page = self._operations.configure_fleet(self.fleet_id, slot_rules, rival=target)

        self._report('fleet_ready', rival=target)
        self._wait(0.5)  # 断点⑤：编队完成后 (尚未出征)

        # 出征前最后一个可交接点。
        ship_stats = self._operations.prepare_battle(page, self.plan)

        self._report('before_start', rival=target)
        self._wait(0.2)

        # 6、点击出征并等待战斗页面稳定。
        self._operations.start_battle(page, rival=target)
        time.sleep(1.0)  # 战斗进入过渡 — 原子段内, 不响应暂停

        # 7、调用战斗引擎完成本场演习。
        result = self._run_combat(ship_stats)

        # 战斗引擎在停止/SL/船坞满时也可能返回结果对象；这些不是成功的
        # 演习轮次，交给处理器按异常或停止协议收口，不能计入进度。
        if self._stop.is_set():
            self._check_pause()
        if result.flag is not ConditionFlag.OPERATION_SUCCESS:
            raise RuntimeError(f'演习战斗未成功: {result.flag.value}')

        # 8、记录成功场次和战果。
        self.progress['fought'] = self.progress.get('fought', 0) + 1
        _log.info('[Exercise] 战斗结束，演习结果：{}', result.flag.value)
        self._report('rival_done', rival=target, fought=self.progress['fought'])
        return result

    # ── 战斗执行 ───────────────────────────────────────────────

    def _run_combat(self, ship_stats: list[ShipDamageState]) -> CombatResult:
        """构建 CombatPlan 并执行战斗 (原子操作: 执行期间不响应暂停)。"""
        return run_battle(
            self.ctx,
            self.plan,
            ship_stats=ship_stats,
            stop_requested=self._stop.is_set,
        )

    # ── 业务辅助 ───────────────────────────────────────────────

    def _has_quota(self) -> bool:
        """配额检查: 完整模式恒为 True; 限额模式在累计计数达到上限前为 True。"""
        return self.rivals_limit is None or self.progress.get('fought', 0) < self.rivals_limit
