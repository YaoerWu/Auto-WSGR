"""战斗引擎 — 状态机主循环。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from autowsgr.application.combat.actions import click_speed_up, dismiss_resource_confirm
from autowsgr.application.combat.engine.state import CombatPhase, ModeCategory, resolve_successors
from autowsgr.application.combat.node_tracker import MapNodeData, NodeTracker
from autowsgr.application.combat.recognizer import (
    CombatRecognitionTimeoutError,
    CombatRecognizer,
    CombatStopRequestedError,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import ConditionFlag, Formation, ShipDamageState


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import numpy as np

    from autowsgr.common.device import AndroidController
    from autowsgr.common.vision import OCREngine

_log = get_logger('combat')
_log_sm = get_logger('combat.engine')  # 状态机转移专用，可单独静默


# ═══════════════════════════════════════════════════════════════════════════════
# 战斗引擎
# ═══════════════════════════════════════════════════════════════════════════════
class CombatEngine:
    """Generic combat state-machine driver.

    Business code supplies the phase decision mixin and result factories.

    Parameters
    ----------
    device:
        设备控制器 (截图 + 触控)。
    ocr:
        OCR 引擎实例 (阵型识别用)。可选，为 ``None`` 则跳过阵型识别。
    """

    def __init__(
        self,
        device: AndroidController,
        ocr: OCREngine | None = None,
        *,
        stop_requested: Callable[[], bool] | None = None,
        history_factory: Callable[[], Any] | None = None,
        result_factory: Callable[[Any], Any] | None = None,
        mode_categories: Mapping[str, ModeCategory] | None = None,
    ) -> None:
        self._device = device
        self._ocr = ocr
        self._stop_requested = stop_requested or (lambda: False)
        self._history_factory = history_factory
        self._result_factory = result_factory
        self._mode_categories = mode_categories or {}

        # 运行时状态 (由 fight() 重置)
        self._plan: Any = None
        self._recognizer: CombatRecognizer = None  # type: ignore[assignment]  # set in fight()
        self._phase = CombatPhase.PROCEED
        self._last_action = 'yes'
        self._node = '0'
        self._ship_stats: list[ShipDamageState] = [ShipDamageState.NORMAL] * 6
        self._history: Any = None
        self._node_count = 0

        # 节点跟踪器 (仅常规战模式有效，由 fight() 初始化)
        self._tracker: NodeTracker | None = None

        # 节点级临时状态
        self._formation_by_rule: Formation | None = None

    # ═══════════════════════════════════════════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════════════════════════════════════════

    def fight(  # noqa: PLR0912
        self,
        plan: Any,
        initial_ship_stats: list[ShipDamageState],
    ) -> Any:
        """执行一次完整的战斗循环。

        从当前状态开始，循环执行:
        ``update_state → make_decision`` 直到战斗结束或 SL。

        Parameters
        ----------
        plan:
            作战计划 (阵型、夜战、节点决策等)。
        initial_ship_stats:
            初始血量状态（来自出征准备页面的检测结果）。

        Returns
        -------
        CombatResult
        """
        self._plan = plan
        self._recognizer = CombatRecognizer(
            self._device,
            stop_requested=self._stop_requested,
        )
        if self._history_factory is None or self._result_factory is None:
            raise RuntimeError('CombatEngine 需要业务层提供 history/result factory')
        self._history = self._history_factory()
        self._reset()

        # 常规战 / 活动战模式下加载地图节点数据并初始化节点追踪器
        if plan.mode == 'normal':
            map_data = MapNodeData.load(plan.chapter, plan.map_id)
            if map_data is not None:
                self._tracker = NodeTracker(map_data)
                _log.info(
                    '[Combat] 节点追踪器已加载: {}-{} ({} 个节点)',
                    plan.chapter,
                    plan.map_id,
                    len(map_data),
                )
            else:
                self._tracker = None
                _log.warning(
                    '[Combat] 无法加载地图数据 {}-{}，节点追踪将不可用',
                    plan.chapter,
                    plan.map_id,
                )
        elif plan.mode == 'event' and plan.event_name:
            map_data = MapNodeData.load_event(
                plan.event_name,
                plan.chapter,
                plan.map_id,
                plan.entrance,
            )
            if map_data is not None:
                self._tracker = NodeTracker(map_data)
                _log.info(
                    '[Combat] 活动节点追踪器已加载: {}/{}-{} ({} 个节点)',
                    plan.event_name,
                    plan.chapter,
                    plan.map_id,
                    len(map_data),
                )
            else:
                self._tracker = None
                _log.warning(
                    '[Combat] 无法加载活动地图数据 {}/{}-{}，节点追踪将不可用',
                    plan.event_name,
                    plan.chapter,
                    plan.map_id,
                )
        else:
            self._tracker = None

        if initial_ship_stats is not None:
            self._ship_stats = initial_ship_stats[:]

        result = self._result_factory(self._history)

        while True:
            try:
                decision = self._step()
            except CombatStopRequestedError:
                _log.info('[Combat] 收到停止请求，正在退出战斗')
                result.flag = ConditionFlag.FIGHT_END
                break
            except CombatRecognitionTimeoutError as e:
                _log.warning('[Combat] 状态识别超时: {}', e)
                if self._try_recovery():
                    continue
                result.flag = ConditionFlag.SL
                break

            if decision == ConditionFlag.FIGHT_CONTINUE:
                continue
            elif decision == ConditionFlag.DOCK_FULL:
                _log.warning('[Combat] 战斗进入失败：船坞已满')
                result.flag = ConditionFlag.DOCK_FULL
                break
            elif decision == ConditionFlag.SL:
                result.flag = ConditionFlag.SL
                break
            elif decision == ConditionFlag.FIGHT_END:
                _log.debug('[Combat] 战斗已结束，日志: {}', self._history)
                result.flag = ConditionFlag.OPERATION_SUCCESS
                break

        result.ship_stats = self._ship_stats[:]
        result.node_count = self._node_count
        _log.info(
            '[Combat] 战斗结束: {} (节点数={})',
            result.flag.value,
            result.node_count,
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════════════════
    def _is_map_routing_phase(self, last_phase: CombatPhase) -> bool:
        return (
            last_phase
            in (CombatPhase.PROCEED, CombatPhase.FIGHT_CONDITION, CombatPhase.START_FIGHT)
            or self._last_action == 'detour'
        )

    def _reset(self) -> None:
        """重置运行时状态。"""
        self._history.reset()
        self._node = '0'
        self._node_count = 0
        self._formation_by_rule = None

        # 重置节点追踪器
        if self._tracker is not None:
            self._tracker.reset()

        self._phase = CombatPhase.START_FIGHT
        self._last_action = ''

    def _step(self) -> ConditionFlag:
        """执行一步: 状态更新 + 决策。"""
        new_phase = self._update_state()
        return self._make_decision(new_phase)

    def _update_state(self) -> CombatPhase:
        """等待并识别下一个状态。"""
        last_phase = self._phase

        candidates = resolve_successors(
            self._plan.transitions,
            self._phase,
            self._last_action,
        )

        _log_sm.debug(
            '[Combat] 当前: {} (action={}) → 候选: {}',
            last_phase.name,
            self._last_action,
            [c.name for c in candidates],
        )

        # 构建轮询间动作（加速点击 + 节点追踪）
        poll_action = self._get_poll_action(last_phase)
        new_phase = self._recognizer.wait_for_phase(
            candidates,
            poll_action=poll_action,
        )

        self._phase = new_phase
        return new_phase

    def _get_poll_action(self, last_phase: CombatPhase) -> Callable[[np.ndarray], None] | None:
        """根据当前状态和模式大类，返回每轮匹配前执行的动作。

        MAP 模式下，地图移动期间执行加速点击、节点追踪、资源弹窗点掉；
        SINGLE 模式下仅加速点击。
        """
        category = self._mode_categories.get(self._plan.mode)
        if self._phase is CombatPhase.FIGHT_PERIOD:
            return lambda _: time.sleep(0.5)
        if category is ModeCategory.MAP:
            if self._is_map_routing_phase(last_phase):
                tracker = self._tracker
                device = self._device

                def _poll_map(screen: np.ndarray) -> None:
                    click_speed_up(device)
                    if tracker is not None:
                        tracker.update_ship_position(screen)
                        new_node = tracker.update_node()
                        if new_node != self._node:
                            self._node = new_node
                        dismiss_resource_confirm(device, screen)

                return _poll_map

        elif category is ModeCategory.SINGLE and last_phase is CombatPhase.START_FIGHT:

            def _poll_single(_: np.ndarray) -> None:
                click_speed_up(self._device)

            return _poll_single

        return None

    # ═══════════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_current_decision(self) -> Any:
        """Return the current business decision (implemented by the host)."""
        raise NotImplementedError

    def _try_recovery(self) -> bool:
        """尝试从错误中恢复。"""
        _log.warning('[Combat] 尝试错误恢复...')
        time.sleep(3.0)

        screen = self._device.screenshot()
        end_phase = self._plan.end_phase
        result = self._recognizer.identify_current(screen, [end_phase])
        if result is not None:
            self._phase = end_phase
            return True
        return False

    def set_node(self, node: str) -> None:
        """设置当前节点（外部调用，如地图追踪更新）。"""
        self._node = node

    @property
    def current_node(self) -> str:
        """当前节点。"""
        return self._node

    @property
    def history(self) -> Any:
        """战斗历史。"""
        return self._history
