"""模块功能：战斗节点的业务决策。

索敌成功后按规则决定撤退、迂回还是开打，按节点规则选阵型，按舰队血量决定
继续前进还是回港。规则本身在 rules 层，这里只负责把它接到画面上。

上层调用：
- application.combat.engine.handlers：阶段分派命中这三步时调用对应处理。

下层依赖：
- application.combat.rules：编成规则与血量判定。
- controller.sortie.battle_engine：点击动作、模板探测与敌情识别。
- application.combat.types：BattlePlan / BattleNodeDecision（引擎对编排层的契约）。

边界：只做「这一步该点哪个按钮」的决策；不认阶段、不推进状态机。
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from autowsgr.application.combat.history import CombatEvent, CombatHistory, EventType
from autowsgr.application.combat.rules import RuleResult, check_blood
from autowsgr.application.combat.types import CombatMode, ConditionFlag, Formation, ShipDamageState
from autowsgr.application.controller.sortie.battle_engine.constants import PHASE_TEMPLATES
from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    check_template_exist,
    read_enemy_composition,
    read_enemy_formation,
)
from autowsgr.application.controller.sortie.battle_engine.page import (
    click_enter_fight,
    click_formation,
    click_proceed,
    click_retreat,
    click_template,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import expect_template
from autowsgr.common.vision.adapters.template_matching import load_template


if TYPE_CHECKING:
    from autowsgr.application.combat.types import BattlePlan
    from autowsgr.common.vision import Template
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')

_DETOUR_LEAVE_ATTEMPTS = 33
"""点下迂回后等待索敌浮窗消失的识别次数（约 10 秒）。"""

_DETOUR_LEAVE_INTERVAL_SECONDS = 0.3
"""等待索敌浮窗消失时每次识别之间的间隔。"""


class CombatDecisionMixin:
    """战斗节点的业务决策。

    Attributes:
        _ctx: 提供设备服务的统一 ContextHandle。
        _plan: 当前作战计划。
        _node: 当前所在节点名。
        _last_action: 上一次决策动作，用于判断阵型是否来自索敌。
        _ship_stats: 六槽位血量状态。
        _history: 战斗历史。
        _formation_by_rule: 索敌时规则指定的阵型，等待阵型阶段消费。
        _node_count: 已走过的节点数。
    """

    _ctx: ContextHandle
    _plan: BattlePlan
    _node: str
    _last_action: str
    _ship_stats: list[ShipDamageState]
    _history: CombatHistory
    _formation_by_rule: Formation | None
    _node_count: int

    # ── 索敌与阵型决策 ─────────────────────────────────────────

    def _handle_spot_enemy(self) -> ConditionFlag:  # noqa: PLR0912
        """采集敌方编成并按规则选择撤退、迂回或进入战斗。

        Returns:
            结束本场返回 FIGHT_END，继续战斗返回 FIGHT_CONTINUE。
        """
        mode = 'exercise' if self._plan.mode == CombatMode.EXERCISE else 'fight'
        enemies = read_enemy_composition(self._ctx, mode=mode)
        enemy_formation = read_enemy_formation(self._ctx)
        _log.info('[COMBAT] 敌方编成：{} 阵型：{}', enemies, enemy_formation)

        decision = self._get_current_decision()
        if not self._plan.is_selected_node(self._node):
            click_retreat(self._ctx)
            self._last_action = 'retreat'
            self._history.add(
                CombatEvent(
                    event_type=EventType.SPOT_ENEMY,
                    node=self._node,
                    action='撤退',
                    extra={'reason': '不在预设点'},
                )
            )
            return ConditionFlag.FIGHT_END

        can_detour = check_template_exist(
            self._ctx,
            _load_template(PHASE_TEMPLATES['bypass']),
            confidence=0.8,
        )
        want_detour = can_detour and decision.detour
        rule_action = None
        if decision.formation_rules and enemy_formation:
            rule_action = decision.formation_rules.evaluate_formation(enemy_formation)
        if (
            rule_action is None or rule_action.result == RuleResult.NO_ACTION
        ) and decision.enemy_rules:
            rule_action = decision.enemy_rules.evaluate(enemies)

        if rule_action is not None:
            if rule_action.result == RuleResult.RETREAT:
                click_retreat(self._ctx)
                self._last_action = 'retreat'
                self._history.add(
                    CombatEvent(
                        event_type=EventType.SPOT_ENEMY,
                        node=self._node,
                        action='撤退',
                        enemies=enemies.copy(),
                    )
                )
                return ConditionFlag.FIGHT_END
            if rule_action.result == RuleResult.DETOUR:
                if not can_detour:
                    _log.error('[COMBAT] 规则指定迂回，但该点无法迂回')
                    raise ValueError('该点无法迂回，但在规则中指定了迂回')
                want_detour = True
            if rule_action.result == RuleResult.FORMATION and rule_action.formation:
                self._formation_by_rule = rule_action.formation

        if want_detour:
            clicked = click_template(
                self._ctx,
                _load_template(PHASE_TEMPLATES['bypass']),
                attempts=8,
            )
            if clicked:
                _log.info('[COMBAT] 执行迂回')
                expect_template(
                    self._ctx,
                    template=_load_template(PHASE_TEMPLATES['spot_enemy']),
                    confidence=0.8,
                    attempts=_DETOUR_LEAVE_ATTEMPTS,
                    interval_seconds=_DETOUR_LEAVE_INTERVAL_SECONDS,
                    absent=True,
                )
            else:
                _log.warning('[COMBAT] 未找到迂回按钮')
            self._last_action = 'detour'
            self._history.add(
                CombatEvent(
                    event_type=EventType.SPOT_ENEMY,
                    node=self._node,
                    action='迂回',
                    enemies=enemies.copy(),
                )
            )
            return ConditionFlag.FIGHT_CONTINUE

        if decision.long_missile_support:
            clicked = click_template(
                self._ctx,
                _load_template(PHASE_TEMPLATES['missile_support']),
                attempts=8,
            )
            if clicked:
                _log.info('[COMBAT] 开启远程导弹支援')
            else:
                _log.warning('[COMBAT] 未找到远程支援按钮')

        click_enter_fight(self._ctx)
        self._last_action = 'fight'
        self._history.add(
            CombatEvent(
                event_type=EventType.SPOT_ENEMY,
                node=self._node,
                action='战斗',
                enemies=enemies.copy(),
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    def _handle_formation(self) -> ConditionFlag:
        """按节点规则选择阵型。

        Returns:
            需要重来返回 SL，否则返回 FIGHT_CONTINUE。
        """
        decision = self._get_current_decision()
        is_from_spot_enemy = self._last_action in ('fight', 'detour')

        if not self._plan.is_selected_node(self._node):
            self._history.add(
                CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action='SL',
                    extra={'reason': '不在预设点'},
                )
            )
            return ConditionFlag.SL

        if is_from_spot_enemy and self._last_action == 'detour' and decision.SL_when_detour_fails:
            self._history.add(
                CombatEvent(
                    event_type=EventType.DETOUR,
                    node=self._node,
                    result='失败',
                )
            )
            self._history.add(
                CombatEvent(
                    event_type=EventType.FORMATION,
                    node=self._node,
                    action='SL',
                )
            )
            return ConditionFlag.SL

        formation = decision.formation
        if is_from_spot_enemy and self._formation_by_rule is not None:
            formation = self._formation_by_rule
            self._formation_by_rule = None
            _log.debug('[COMBAT] 使用规则阵型：{}', formation.name)
        elif not is_from_spot_enemy:
            if decision.SL_when_spot_enemy_fails:
                self._history.add(
                    CombatEvent(
                        event_type=EventType.FORMATION,
                        node=self._node,
                        action='SL',
                        extra={'reason': '索敌失败'},
                    )
                )
                return ConditionFlag.SL
            if decision.formation_when_spot_enemy_fails is not None:
                formation = decision.formation_when_spot_enemy_fails

        click_formation(self._ctx, formation)
        self._last_action = str(formation.value)
        self._history.add(
            CombatEvent(
                event_type=EventType.FORMATION,
                node=self._node,
                action=f'阵型{formation.value} ({formation.name})',
            )
        )
        return ConditionFlag.FIGHT_CONTINUE

    # ── 节点推进 ─────────────────────────────────────────────

    def _handle_proceed(self) -> ConditionFlag:
        """按战术规则决定继续前进或回港。

        Returns:
            继续前进返回 FIGHT_CONTINUE，回港返回 FIGHT_END。
        """
        self._node_count += 1
        decision = self._get_current_decision()
        should_proceed = decision.proceed and check_blood(
            self._ship_stats,
            decision.proceed_stop,
        )
        _log.info('[COMBAT] 继续前进决策：{}', '前进' if should_proceed else '回港')
        click_proceed(self._ctx, go_forward=should_proceed)
        self._last_action = 'yes' if should_proceed else 'no'
        self._history.add(
            CombatEvent(
                event_type=EventType.PROCEED,
                node=self._node,
                action='前进' if should_proceed else '回港',
                ship_stats=self._ship_stats[:],
            )
        )
        return ConditionFlag.FIGHT_CONTINUE if should_proceed else ConditionFlag.FIGHT_END


@cache
def _load_template(relative_path: str) -> Template:
    """加载战斗模板；同一路径只读盘一次。"""
    return load_template(relative_path)


__all__ = ['CombatDecisionMixin']
