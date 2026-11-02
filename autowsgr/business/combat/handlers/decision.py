"""战斗业务决策。

本模块只保留依赖战斗计划和业务规则的节点决策；通用阶段动作由 application
提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.combat import (
    click_enter_fight,
    click_formation,
    click_image,
    click_proceed,
    click_retreat,
    get_enemy_formation,
    get_enemy_info,
    image_exist,
)
from autowsgr.application.combat.history import CombatEvent, CombatHistory, EventType
from autowsgr.business.combat.plan import CombatMode, CombatPlan, NodeDecision
from autowsgr.business.combat.rules import RuleResult, check_blood
from autowsgr.common.device.interaction import wait_leave_page
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import ConditionFlag, Formation, ShipDamageState
from autowsgr.common.vision import ImageChecker
from autowsgr.common.vision.resources import TemplateKey


if TYPE_CHECKING:
    from autowsgr.common.device import AndroidController
    from autowsgr.common.vision import OCREngine


_log = get_logger('combat')


class CombatDecisionMixin:
    """战斗节点的业务决策。

    计划和规则留在业务层；阶段分发和结算动作由 application mixin 提供。
    """

    _device: AndroidController
    _plan: CombatPlan
    _ocr: OCREngine | None
    _node: str
    _last_action: str
    _ship_stats: list[ShipDamageState]
    _history: CombatHistory
    _formation_by_rule: Formation | None

    # ── 索敌与阵型决策 ─────────────────────────────────────────

    def _handle_spot_enemy(self) -> ConditionFlag:  # noqa: PLR0912
        """采集敌方编成并按业务规则选择撤退、迂回或进入战斗。"""
        mode = 'exercise' if self._plan.mode == CombatMode.EXERCISE else 'fight'
        enemies = get_enemy_info(self._device, mode=mode)
        enemy_formation = get_enemy_formation(self._device, self._ocr)
        _log.info('[Combat] 敌方编成: {} 阵型: {}', enemies, enemy_formation)

        decision = self._get_current_decision()
        if not self._plan.is_selected_node(self._node):
            click_retreat(self._device)
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

        can_detour = image_exist(self._device, TemplateKey.BYPASS, 0.8)
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
                click_retreat(self._device)
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
                    _log.error('[Combat] 规则指定迂回, 但该点无法迂回')
                    raise ValueError('该点无法迂回, 但在规则中指定了迂回')
                want_detour = True
            if rule_action.result == RuleResult.FORMATION and rule_action.formation:
                self._formation_by_rule = rule_action.formation

        if want_detour:
            clicked = click_image(self._device, TemplateKey.BYPASS, 2.5)
            if clicked:
                _log.info('[Combat] 执行迂回')
                spot_templates = TemplateKey.SPOT_ENEMY.templates
                wait_leave_page(
                    self._device,
                    checker=lambda screen: (
                        ImageChecker.find_any(screen, spot_templates, confidence=0.8) is not None
                    ),
                    timeout=10.0,
                    source='spot_enemy_success',
                    target='map_routing',
                )
            else:
                _log.warning('[Combat] 未找到迂回按钮')
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
            clicked = click_image(self._device, TemplateKey.MISSILE_SUPPORT, 2.5)
            if clicked:
                _log.info('[Combat] 开启远程导弹支援')
            else:
                _log.warning('[Combat] 未找到远程支援按钮')

        click_enter_fight(self._device)
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
        """按节点规则选择阵型。"""
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
            _log.debug('[Combat] 使用规则阵型: {}', formation.name)
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

        click_formation(self._device, formation)
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
        """按战术规则决定继续前进或回港。"""
        self._node_count += 1
        decision = self._get_current_decision()
        should_proceed = decision.proceed and check_blood(
            self._ship_stats,
            decision.proceed_stop,
        )
        _log.info('[Combat] 继续前进决策: {}', '前进' if should_proceed else '回港')
        click_proceed(self._device, go_forward=should_proceed)
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

    def _get_current_decision(self) -> NodeDecision:
        """返回当前节点的业务决策，由组合引擎实现。"""
        raise NotImplementedError


__all__ = ['CombatDecisionMixin']
