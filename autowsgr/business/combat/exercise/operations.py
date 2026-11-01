"""演习执行器使用的页面操作和准备流程实现。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.ui.controller.fleet import (
    BattlePreparationPage,
    RepairStrategy,
)
from autowsgr.application.ui.controller.operations.sortie_page.main_page import (
    SortiePage,
    SortieTab,
)
from autowsgr.application.ui.controller.sortie.exercise import ExercisePage
from autowsgr.common.device.interaction import NavigationError
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import RepairMode, ShipDamageState


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.runtime import RuntimeContext as GameContext
    from autowsgr.business.combat.fleet import FleetSlotRule
    from autowsgr.business.combat.plan import CombatPlan

_log = get_logger('business.combat.exercise')


class ExerciseOperations:
    """提供演习流程所需的页面操作，不决定任务循环和终态。"""

    def __init__(
        self,
        ctx: GameContext,
        *,
        wait: Callable[[float], None],
        report: Callable[..., None],
    ) -> None:
        self.ctx = ctx
        self._wait = wait
        self._report = report

    def switch_to_exercise_panel(self) -> None:
        """在地图页切换到演习面板。"""
        SortiePage(self.ctx).click_tab(SortieTab.EXERCISE)
        self._report('panel_ready')

    def pick_rival(self, rival: int | None) -> int | None:
        """读取可挑战对手并返回指定或最靠前的一个。"""
        rivals = ExercisePage(self.ctx).read_exercise_rival_status().rivals
        if rival is not None:
            return rival if rivals[rival - 1] else None
        return next((index for index, available in enumerate(rivals, start=1) if available), None)

    def select_rival(self, rival: int) -> None:
        """选择一个对手。"""
        _log.info('[Exercise] 选择对手：{}号', rival)
        ExercisePage(self.ctx).select_exercise_rival(rival)

    def enter_battle(self) -> None:
        """从对手预览页进入出征准备页。"""
        ExercisePage(self.ctx).enter_exercise_battle()

    def configure_fleet(
        self,
        fleet_id: int,
        slot_rules: Sequence[FleetSlotRule] | None,
        *,
        rival: int,
    ) -> BattlePreparationPage:
        """选择舰队并按规则完成编队。"""
        page = BattlePreparationPage(self.ctx)
        page.select_fleet(fleet_id)
        _log.info('[Exercise] 选择队伍：{}', fleet_id)
        _log.info('[Exercise] 进入舰队编成')
        self._report('formation_entered', rival=rival)
        self._wait(0.2)

        if slot_rules is None:
            _log.info('[Exercise] 当前队伍已满足演习编队（未提供替换规则）')
            return page

        for slot, rule in enumerate(slot_rules[:6], start=1):
            for option in rule.options:
                _log.info(
                    '[Exercise] 开始选择 {} 号位舰船：{}（{}校验）',
                    slot,
                    option.name,
                    '宽泛' if option.relaxed_constraints else '严格',
                )

        page.adjust_fleet(
            fleet_id=fleet_id,
            fleet_rules=slot_rules,
            task_type='exercise',
            on_event=self._on_fleet_event,
        )
        return page

    def prepare_battle(
        self,
        page: BattlePreparationPage,
        plan: CombatPlan,
    ) -> list[ShipDamageState]:
        """执行补给、快速维修和出征前船损识别。"""
        page.apply_supply()
        strategy = self.repair_strategy(plan)
        if strategy is not None:
            page.apply_repair(strategy)
        damage = page.read_ship_damage()
        return [damage.get(index, ShipDamageState.NORMAL) for index in range(6)]

    def start_battle(self, page: BattlePreparationPage, *, rival: int) -> None:
        """点击出征并上报进入战斗。"""
        for attempt in range(2):
            if page.try_start_battle(target='exercise combat'):
                _log.info('[Exercise] 进入战斗')
                self._report('battle_started', rival=rival)
                return
            if attempt == 0:
                _log.warning('[Exercise] 出征后仍在准备页，重试一次')
        raise NavigationError('演习出征后仍停留在准备页')

    @staticmethod
    def repair_strategy(plan: CombatPlan) -> RepairStrategy | None:
        """将作战计划的修理阈值转换为准备页策略。"""
        modes = plan.repair_mode if isinstance(plan.repair_mode, list) else [plan.repair_mode]
        value = min(mode.value if isinstance(mode, RepairMode) else int(mode) for mode in modes)
        if value <= RepairMode.moderate_damage.value:
            return RepairStrategy.MODERATE
        if value <= RepairMode.severe_damage.value:
            return RepairStrategy.SEVERE
        return None

    def _on_fleet_event(self, event: str, **data: Any) -> None:
        """记录编队事件并在单艘选船完成后检查暂停。"""
        if event == 'fleet_validation':
            _log.info('[Exercise] 当前队伍{}满足演习编队', '已' if data.get('passed') else '不')
            self._report(event, **data)
        elif event == 'ship_selected':
            option = data.get('option')
            selected = data.get('selected') or '未识别'
            _log.info(
                '[Exercise] 开始替换 {} 号位舰船：{} → {}',
                data.get('slot', '?'),
                getattr(option, 'name', '目标'),
                selected,
            )
            self._report(
                event,
                slot=data.get('slot'),
                expected=getattr(option, 'name', None),
                actual=selected,
            )
            self._wait(0)
        elif event == 'ship_removed':
            self._report('ship_selected', slot=data.get('slot'), actual=None)
            self._wait(0)
        elif event == 'ship_moved':
            _log.info(
                '[Exercise] 开始移动 {} 号位到 {} 号位位置',
                data.get('source', '?'),
                data.get('destination', '?'),
            )
        elif event == 'fleet_result':
            members = [name for name in data.get('members', []) if name]
            _log.info('[Exercise] 舰队编成完毕成员为：{}', '、'.join(members))
            self._report(event, **data)
