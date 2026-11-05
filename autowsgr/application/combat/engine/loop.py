"""模块功能：战斗主循环。

上层调用：
- application.combat.service：一次完整战斗的唯一执行体力。

下层依赖：
- application.combat.engine.recognizer：等待下一个阶段出现。
- application.combat.engine.handlers：按阶段分派处理器。
- application.combat.node_tracking：地图模式下的节点追踪。
- controller.sortie.battle_engine.page：点加速与关确认弹窗。

边界：只管一场战斗从点下出征到退出战果页；不负责进图、编队、补给修理，
也不决定打几场。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.combat.engine.decision import CombatDecisionMixin
from autowsgr.application.combat.engine.handlers import CombatHandlersMixin
from autowsgr.application.combat.engine.preparation import accelerate
from autowsgr.application.combat.engine.recognizer import CombatRecognizer
from autowsgr.application.combat.engine.settlement import CombatSettlementMixin
from autowsgr.application.combat.engine.transitions import (
    MODE_CATEGORIES,
    resolve_successors,
)
from autowsgr.application.combat.engine.types import CombatPhase
from autowsgr.application.combat.errors import (
    CombatRecognitionTimeoutError,
    CombatStopRequestedError,
)
from autowsgr.application.combat.history import CombatHistory, CombatResult
from autowsgr.application.combat.node_tracking import MapNodeData, NodeTracker
from autowsgr.application.combat.types import (
    CombatMode,
    ConditionFlag,
    Formation,
    ModeCategory,
    ShipDamageState,
)
from autowsgr.application.controller.sortie.battle_engine.page import (
    click_speed_up,
    dismiss_resource_confirm,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import screenshot


if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy

    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')
_log_state = get_logger('combat.engine')


class CombatLoop(CombatHandlersMixin, CombatDecisionMixin, CombatSettlementMixin):
    """一场战斗的主循环。

    循环体只有两件事：等下一个阶段出现，按阶段做一次决策。战斗结束由阶段
    处理器返回的 :class:`ConditionFlag` 决定。

    Args:
        ctx: 上下文句柄，提供设备与截图。
        stop_requested: 可选的停止询问函数。
    """

    def __init__(
        self,
        ctx: ContextHandle,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._ctx = ctx
        self._stop_requested = stop_requested or (lambda: False)
        self._recognizer = CombatRecognizer(ctx, stop_requested=self._stop_requested)

        # 运行期状态，每次 run() 重置。
        self._plan: object | None = None
        self._phase = CombatPhase.PROCEED
        self._last_action = 'yes'
        self._node = '0'
        self._ship_stats: list[ShipDamageState] = [ShipDamageState.NORMAL] * 6
        self._history = CombatHistory()
        self._node_count = 0
        self._formation_by_rule: Formation | None = None
        self._tracker: NodeTracker | None = None

    def run(
        self,
        plan: object,
        initial_ship_stats: list[ShipDamageState],
    ) -> CombatResult:
        """执行一场完整战斗。

        Args:
            plan: 作战计划，鸭子类型提供 mode / transitions / end_phase /
                collect_result_info / fight_condition / night 等字段。
            initial_ship_stats: 开打前的我方血量状态。

        Returns:
            本次战斗的结果。
        """
        self._plan = plan
        self._history = CombatHistory()
        self._load_tracker(plan)
        if initial_ship_stats is not None:
            self._ship_stats = list(initial_ship_stats)
        self._reset()

        result = CombatResult(history=self._history)

        while True:
            try:
                decision = self._step()
            except CombatStopRequestedError:
                _log.info('[COMBAT] 收到停止请求，正在退出战斗')
                result.flag = ConditionFlag.FIGHT_END
                break
            except CombatRecognitionTimeoutError as error:
                _log.warning('[COMBAT] 状态识别超时：{}', error)
                if self._try_recovery():
                    continue
                result.flag = ConditionFlag.SL
                break

            if decision == ConditionFlag.FIGHT_CONTINUE:
                continue
            if decision == ConditionFlag.DOCK_FULL:
                result.flag = ConditionFlag.DOCK_FULL
                break
            if decision == ConditionFlag.SL:
                result.flag = ConditionFlag.SL
                break
            if decision == ConditionFlag.FIGHT_END:
                _log.debug('[COMBAT] 战斗结束，日志={}', self._history)
                result.flag = ConditionFlag.OPERATION_SUCCESS
                break

        result.ship_stats = list(self._ship_stats)
        result.node_count = self._node_count
        _log.info('[COMBAT] 战斗结束：{}，节点数={}', result.flag.value, result.node_count)
        return result

    @property
    def history(self) -> CombatHistory:
        """战斗历史。"""
        return self._history

    def _get_current_decision(self) -> object:
        """返回当前节点的业务决策，节点推进时由计划按节点名查表。"""
        return self._plan.get_node_decision(self._node)

    def _load_tracker(self, plan: object) -> None:
        """按作战模式加载地图节点数据。"""
        mode = getattr(plan, 'mode', None)
        if mode == CombatMode.NORMAL:
            map_data = MapNodeData.load(plan.chapter, plan.map_id)
            self._attach_tracker(map_data, f'{plan.chapter}-{plan.map_id}')
        elif mode == CombatMode.EVENT and getattr(plan, 'event_name', None):
            map_data = MapNodeData.load_event(
                plan.event_name,
                plan.chapter,
                plan.map_id,
                plan.entrance,
            )
            self._attach_tracker(
                map_data,
                f'{plan.event_name}/{plan.chapter}-{plan.map_id}',
            )
        else:
            self._tracker = None

    def _attach_tracker(self, map_data: MapNodeData | None, label: str) -> None:
        """挂上节点追踪器；地图数据缺失时退回无追踪。"""
        if map_data is None:
            self._tracker = None
            _log.warning('[COMBAT] 地图数据缺失：{}，节点追踪不可用', label)
            return
        self._tracker = NodeTracker(map_data)
        _log.info('[COMBAT] 节点追踪器已加载：{}（{} 个节点）', label, len(map_data))

    def _reset(self) -> None:
        """重置一次战斗的运行期状态。"""
        self._history.reset()
        self._node = '0'
        self._node_count = 0
        if self._tracker is not None:
            self._tracker.reset()
        self._phase = CombatPhase.START_FIGHT
        self._last_action = ''
        self._formation_by_rule = None

    def _step(self) -> ConditionFlag:
        """走一步：等下一个阶段，然后做一次决策。"""
        return self._make_decision(self._update_state())

    def _update_state(self) -> CombatPhase:
        """等待并识别下一个阶段。"""
        last_phase = self._phase
        candidates = resolve_successors(
            self._plan.transitions,
            self._phase,
            self._last_action,
        )
        _log_state.debug(
            '[COMBAT] 当前阶段={}（action={}）→ 候选={}',
            last_phase.name,
            self._last_action,
            [candidate.name for candidate in candidates],
        )
        self._phase = self._recognizer.wait_for_phase(
            candidates,
            poll_action=self._build_poll_action(last_phase),
        )
        return self._phase

    def _build_poll_action(
        self,
        last_phase: CombatPhase,
    ) -> Callable[[numpy.ndarray], None] | None:
        """按当前阶段返回每轮匹配前要做的动作。

        MAP 大类在地图移动期间要边点加速边更新节点；SINGLE 大类只在出征后的
        过场点加速；战斗进行中则放慢轮询节奏，少截几张图。
        """
        if self._phase is CombatPhase.FIGHT_PERIOD:
            return lambda _: time.sleep(0.5)

        category = MODE_CATEGORIES.get(self._plan.mode)
        if category is ModeCategory.MAP and self._is_map_routing_phase(last_phase):
            tracker = self._tracker
            ctx = self._ctx

            def _poll_map(frame: numpy.ndarray) -> None:
                click_speed_up(ctx)
                if tracker is not None:
                    tracker.update_ship_position(frame)
                    self._node = tracker.update_node()
                dismiss_resource_confirm(ctx, frame)

            return _poll_map

        if category is ModeCategory.SINGLE and last_phase is CombatPhase.START_FIGHT:
            ctx = self._ctx

            def _poll_single(_: numpy.ndarray) -> None:
                accelerate(ctx)

            return _poll_single

        return None

    def _is_map_routing_phase(self, last_phase: CombatPhase) -> bool:
        """判断上一阶段是否走在地图路由上。"""
        return (
            last_phase
            in (
                CombatPhase.PROCEED,
                CombatPhase.FIGHT_CONDITION,
                CombatPhase.START_FIGHT,
            )
            or self._last_action == 'detour'
        )

    def _try_recovery(self) -> bool:
        """识别超时后看一眼是不是已经停在终点页，是就当作走完。"""
        _log.warning('[COMBAT] 尝试错误恢复……')
        time.sleep(3.0)

        frame = screenshot(self._ctx)
        end_phase = self._plan.end_phase
        if self._recognizer.identify_current(frame, [end_phase]) is None:
            return False
        self._phase = end_phase
        return True


__all__ = ['CombatLoop']
