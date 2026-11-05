"""模块功能：战斗阶段的分派与通用处理。

上层调用：
- application.combat.engine.loop：每识别到一个阶段就调一次决策。

下层依赖：
- controller.sortie.battle_engine：点击动作与单帧识别。
- application.combat.history：写入战斗事件。

边界：只处理与战斗模式无关的通用阶段动作；战况、阵型、夜战这些要按规则
拍板的处理在 decision.py，战果结算在 settlement.py。
"""

from __future__ import annotations

import time
from functools import cache
from typing import TYPE_CHECKING, Any

from autowsgr.application.combat.engine.preparation import record_dock_full
from autowsgr.application.combat.engine.types import CombatPhase
from autowsgr.application.combat.history import CombatEvent, CombatHistory, EventType
from autowsgr.application.combat.types import ConditionFlag
from autowsgr.application.controller.sortie.battle_engine.constants import PHASE_TEMPLATES
from autowsgr.application.controller.sortie.battle_engine.monitor.checker import is_ship_drop_page
from autowsgr.application.controller.sortie.battle_engine.page import (
    click_fight_condition,
    click_night_battle,
    click_result,
    click_skip_missile_animation,
    click_template,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import screenshot
from autowsgr.common.vision.adapters.template_matching import load_template


if TYPE_CHECKING:
    from autowsgr.application.combat.engine.recognizer import CombatRecognizer
    from autowsgr.common.vision import Template
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


def _phase_handlers() -> dict[CombatPhase, str]:
    """阶段到处理器方法名的映射。"""
    return {
        CombatPhase.FIGHT_CONDITION: '_handle_fight_condition',
        CombatPhase.SPOT_ENEMY_SUCCESS: '_handle_spot_enemy',
        CombatPhase.FORMATION: '_handle_formation',
        CombatPhase.MISSILE_ANIMATION: '_handle_missile_animation',
        CombatPhase.FIGHT_PERIOD: '_handle_fight_period',
        CombatPhase.NIGHT_PROMPT: '_handle_night_prompt',
        CombatPhase.RESULT: '_handle_result',
        CombatPhase.EXP_SETTLEMENT: '_handle_exp_settlement',
        CombatPhase.GET_SHIP: '_handle_get_ship',
        CombatPhase.PROCEED: '_handle_proceed',
        CombatPhase.FLAGSHIP_SEVERE_DAMAGE: '_handle_flagship_severe_damage',
        CombatPhase.DOCK_FULL: '_handle_dock_full',
    }


_PHASE_HANDLERS = _phase_handlers()
"""阶段到处理器方法名。START_FIGHT 是过渡态，没有处理器，靠下一个阶段覆盖。"""


class CombatHandlersMixin:
    """为战斗主循环提供阶段派发与通用处理。

    宿主类需要提供 _ctx / _plan / _node / _last_action / _ship_stats /
    _history / _recognizer / _node_count 这些运行期状态。
    """

    _ctx: ContextHandle
    _plan: Any
    _node: str
    _last_action: str
    _ship_stats: list[Any]
    _history: CombatHistory
    _recognizer: CombatRecognizer
    _node_count: int

    def _make_decision(self, phase: CombatPhase) -> ConditionFlag:
        """按当前阶段做一次决策并执行操作。

        Args:
            phase: 当前识别到的阶段。

        Returns:
            流程标记；``FIGHT_END`` 表示这一场已经走完。
        """
        handler_name = _PHASE_HANDLERS.get(phase)
        result = (
            getattr(self, handler_name)()
            if handler_name is not None
            else ConditionFlag.FIGHT_CONTINUE
        )

        if phase == self._plan.end_phase:
            self._history.add(
                CombatEvent(
                    event_type=EventType.AUTO_RETURN,
                    node=self._node,
                    action='正常',
                )
            )
            return ConditionFlag.FIGHT_END
        return result

    # ── 各阶段处理器 ──────────────────────────────────────────────────────────

    def _handle_fight_condition(self) -> ConditionFlag:
        """选择战况。"""
        condition = self._plan.fight_condition
        click_fight_condition(self._ctx, condition)
        self._last_action = str(condition.value)
        self._history.add(
            CombatEvent(
                event_type=EventType.FIGHT_CONDITION,
                node=self._node,
                action=str(condition.value),
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_missile_animation(self) -> ConditionFlag:
        """跳过导弹支援动画。"""
        _log.info('[COMBAT] 跳过导弹支援动画')
        click_skip_missile_animation(self._ctx)
        self._last_action = 'skip_animation'
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_fight_period(self) -> ConditionFlag:
        """战斗进行中：按规则判断要不要在开打前 SL。"""
        if self._get_current_decision().SL_when_enter_fight:
            self._history.add(
                CombatEvent(
                    event_type=EventType.ENTER_FIGHT,
                    node=self._node,
                    action='SL',
                )
            )
            return ConditionFlag.SL
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_night_prompt(self) -> ConditionFlag:
        """选择是否夜战。"""
        pursue = self._get_current_decision().night
        _log.info('[COMBAT] 夜战选择：{}', '追击' if pursue else '撤退')
        click_night_battle(self._ctx, pursue=pursue)
        self._last_action = 'yes' if pursue else 'no'
        self._history.add(
            CombatEvent(
                event_type=EventType.NIGHT_BATTLE,
                node=self._node,
                action='追击' if pursue else '撤退',
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _click_result_until_closed(
        self,
        phase: CombatPhase,
        *,
        attempts: int = 6,
        interval: float = 0.3,
        polls: int = 4,
        pass_through: tuple[CombatPhase, ...] = (),
    ) -> None:
        """点击战果类页面继续，并验证已经到达已知后继状态。

        判据是到达验证而不是原页面消失：点掉战果页后游戏先进入经验结算子页，
        若以「战果页消失」为成功，复检会在经验页提前返回，主循环随后等不到
        任何阶段而超时。

        Args:
            phase: 待关闭的页面阶段（RESULT 或 GET_SHIP）。
            attempts: 最大点击次数。
            interval: 复检轮询间隔（秒）。
            polls: 每次点击后的复检上限。
            pass_through: 识别到就继续点过去的过渡页。
        """
        candidates = [phase, *pass_through, *self._result_successors(phase)]
        for attempt in range(1, attempts + 1):
            click_result(self._ctx)
            for _ in range(polls):
                time.sleep(interval)
                frame = screenshot(self._ctx)
                current = self._recognizer.identify_current(frame, candidates)
                if current is None:
                    # 过渡帧只等待，不点击：盲连点会穿透中间页。掉落页模板在
                    # 动画期间可能不命中，用像素签名兜底，避免漏统计。
                    if CombatPhase.GET_SHIP in candidates and is_ship_drop_page(frame):
                        _log.debug(
                            '[COMBAT] {} 过渡帧命中掉落页签名，捕获掉落',
                            phase.name,
                        )
                        self._capture_get_ship()
                        return
                    continue
                if current in pass_through:
                    _log.debug(
                        '[COMBAT] {} 到达过渡页 {}（第 {} 次点击），继续点击跳过',
                        phase.name,
                        current.name,
                        attempt,
                    )
                    break
                if current == phase:
                    _log.warning(
                        '[COMBAT] {} 页面未关闭（第 {} 次点击），延迟重试',
                        phase.name,
                        attempt,
                    )
                    break
                if current == CombatPhase.GET_SHIP:
                    self._capture_get_ship()
                _log.debug('[COMBAT] {} 已推进到 {}', phase.name, current.name)
                return
            else:
                _log.debug(
                    '[COMBAT] {} 点击后持续无法识别（第 {} 次），等待主循环确认',
                    phase.name,
                    attempt,
                )
                return
        _log.error('[COMBAT] {} 点击 {} 次仍未推进，继续执行', phase.name, attempts)

    def _result_successors(self, phase: CombatPhase) -> list[CombatPhase]:
        """返回战果类页面点击后的合法落点集合。

        比转移图宽：快速点击可能连跳两页，这里把穿透场景也列成到达点，认出来
        就停止点击，交给主循环按当前页继续。

        Args:
            phase: 待关闭的页面阶段。

        Returns:
            可能的到达阶段。
        """
        successors = [CombatPhase.PROCEED, CombatPhase.FLAGSHIP_SEVERE_DAMAGE]
        end_phase = self._plan.end_phase
        if end_phase is not None:
            successors.append(end_phase)
        if phase == CombatPhase.RESULT:
            successors.append(CombatPhase.GET_SHIP)
            if self._plan.collect_result_info:
                successors.append(CombatPhase.EXP_SETTLEMENT)
        elif phase == CombatPhase.EXP_SETTLEMENT:
            successors.append(CombatPhase.GET_SHIP)
        return successors

    def _handle_exp_settlement(self) -> ConditionFlag:
        """经验结算子页：点继续推进到掉落页、前进对话框或终点页。"""
        self._click_result_until_closed(CombatPhase.EXP_SETTLEMENT)
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_get_ship(self) -> ConditionFlag:
        """掉落页：先幂等捕获掉落，再关掉页面。"""
        self._capture_get_ship()
        self._click_result_until_closed(CombatPhase.GET_SHIP)
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_flagship_severe_damage(self) -> ConditionFlag:
        """旗舰大破：点掉提示，强制回港。"""
        _log.info('[COMBAT] 旗舰大破，强制回港')
        click_template(
            self._ctx,
            _load_template(PHASE_TEMPLATES['flagship_damage']),
            attempts=7,
            interval_seconds=0.3,
        )
        time.sleep(0.25)
        self._history.add(
            CombatEvent(
                event_type=EventType.FLAGSHIP_DAMAGE,
                node=self._node,
                action='回港',
            )
        )
        return ConditionFlag.FIGHT_END

    def _handle_dock_full(self) -> ConditionFlag:
        """船坞已满：交回上层处理，不当作一次成功的战斗。"""
        return record_dock_full(self._history, node=self._node)


@cache
def _load_template(relative_path: str) -> Template:
    """加载战斗模板；同一路径只读盘一次。"""
    return load_template(relative_path)


__all__ = ['CombatHandlersMixin']
