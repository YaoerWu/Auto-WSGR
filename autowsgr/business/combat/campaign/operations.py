"""战役页面操作和战前准备。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sortie import SortieTab
from autowsgr.application.errors import ManualRepairRequiredError
from autowsgr.application.ui.controller.fleet import (
    BattlePreparationPage,
    RepairStrategy,
)
from autowsgr.application.ui.controller.operations.sortie_page.campaign_page import CampaignPage
from autowsgr.application.navigation import goto_bath_from_campaign_sortie
from autowsgr.business.combat.fleet import exact_fleet_rules
from autowsgr.business.logistics.repair.bath_repair import repair_manual_targets_in_bath
from autowsgr.common.device.interaction import NavigationError
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import RepairMode, ShipDamageState


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.application.runtime import RuntimeContext as GameContext

    from .spec import CampaignSpec


_log = get_logger('business.combat.campaign')


class CampaignOperations:
    """执行战役用例所需的页面组合操作。"""

    def __init__(
        self,
        ctx: GameContext,
        *,
        wait: Callable[[float], None],
        report: Callable[..., None],
        save_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self._wait = wait
        self._report = report
        self._save_progress = save_progress or (lambda _data: None)

    def enter_campaign(self, spec: CampaignSpec) -> None:
        """从地图页进入指定战役的出征准备页。"""
        page = CampaignPage(self.ctx)
        page.select_tab(SortieTab.CAMPAIGN)
        self._report('panel_ready', campaign=spec.campaign_name)
        self._wait(0)
        page.enter_campaign(
            map_index=spec.map_index,
            difficulty=spec.difficulty,
            campaign_name=spec.campaign_name,
        )

    def prepare_battle(  # noqa: PLR0912 - one campaign preparation flow owns these branches
        self,
        spec: CampaignSpec,
        *,
        reset_fleet: bool = True,
    ) -> tuple[BattlePreparationPage, list[ShipDamageState], list[Any]]:
        """完成编队、修理和战前血量识别。"""
        self._wait(0.25)
        page = BattlePreparationPage(self.ctx)

        selection = spec.fleet_selection
        self._report('formation_entered')
        self._wait(0)
        slot_rules = selection.slot_rules
        if slot_rules is None and selection.plain_fleet is not None:
            slot_rules = exact_fleet_rules(selection.plain_fleet)
        if slot_rules is not None:
            _log.info('[Campaign] 战役队伍加载：编队配置加载成功')
            fleet_snapshot = page.adjust_fleet(
                fleet_id=None,
                fleet_rules=slot_rules,
                task_type='campaign',
                reset_fleet=reset_fleet,
                recognize_ship_types=not spec.skip_ship_type_validation,
                on_event=self._on_fleet_event,
            )
            self._report('fleet_ready', members=fleet_snapshot.names)
        elif spec.required_ship_types is not None:
            if not page.validate_campaign_fleet(
                spec.required_ship_types,
                validate_types=not spec.skip_ship_type_validation,
            ):
                raise RuntimeError('当前舰队不满足困难战役舰种和数量限制')
            _log.info('[Campaign] 战役队伍加载：未配置编队，沿用当前队伍')
            self._report('fleet_ready')
            fleet_snapshot = page.read_fleet_snapshot(
                recognize_ship_types=not spec.skip_ship_type_validation,
            )
        else:
            _log.info('[Campaign] 战役队伍加载：未配置编队，沿用当前队伍')
            self._report('fleet_ready')
            fleet_snapshot = page.read_fleet_snapshot(
                recognize_ship_types=not spec.skip_ship_type_validation,
            )

        strategy = _repair_strategy(spec.plan.repair_mode)
        if strategy is not None:
            if getattr(self.ctx.config, 'repair_manually', False):
                fleet_names = fleet_snapshot.names or selection.primary_names or []
                positions = page.check_repair(strategy)
                if positions:
                    targets = [
                        fleet_names[position]
                        for position in positions
                        if 0 <= position < len(fleet_names) and fleet_names[position]
                    ]
                    if not targets:
                        raise ManualRepairRequiredError('无法解析手动维修目标')
                    try:
                        goto_bath_from_campaign_sortie(self.ctx)
                        dispatched = repair_manual_targets_in_bath(self.ctx, targets)
                    except ManualRepairRequiredError:
                        raise
                    except Exception as exc:
                        raise ManualRepairRequiredError('手动维修处理失败') from exc
                    missing = [name for name in targets if name not in set(dispatched)]
                    if missing:
                        _log.warning('[Campaign] 手动维修未能派出: {}', missing)
                    raise ManualRepairRequiredError('需要手动修理')
            else:
                page.apply_repair(strategy)

        damage = page.read_ship_damage()
        ship_stats = [damage.get(index, ShipDamageState.NORMAL) for index in range(6)]
        ships = [self.ctx.get_ship(name) for name in fleet_snapshot.names if name]
        return page, ship_stats, ships

    def _on_fleet_event(self, event: str, **data: Any) -> None:
        """保存战役编队断点。"""
        if event in {'ship_selected', 'ship_removed'}:
            return
        self._report(event, **data)
        if event not in {'fleet_checkpoint', 'fleet_result'}:
            return
        self._save_progress(
            {
                'stage': data.get('stage', 'complete'),
                'slot': data.get('slot'),
                'members': list(data.get('members', [])),
            },
        )
        if event == 'fleet_checkpoint':
            self._wait(0)

    def start_battle(self, page: BattlePreparationPage) -> bool:
        """点击出征并探测是否离开准备页。"""
        for attempt in range(2):
            if page.try_start_battle(target='campaign combat'):
                _log.info('[Campaign] 战役战斗开始')
                self._report('battle_started')
                return True
            if attempt == 0:
                _log.warning('[Campaign] 出征后仍在准备页，重试一次')

        _log.info('[Campaign] 两次出征均未离开准备页，判定战役次数已用完')
        try:
            page.go_back()
        except NavigationError as error:
            _log.warning('[Campaign] 战役次数耗尽后回退地图失败: {}', error)
        return False


def _repair_strategy(repair_mode: list[RepairMode]) -> RepairStrategy | None:
    value = min(mode.value for mode in repair_mode)
    if value <= RepairMode.moderate_damage.value:
        return RepairStrategy.MODERATE
    if value <= RepairMode.severe_damage.value:
        return RepairStrategy.SEVERE
    return None
