"""模块功能：控制出征准备页并编排舰队准备到开始出征的主流程。

上层调用：
- business.combat：创建页面控制器并执行准备页主流程。
- application.ui.navigation：注册准备页检查器和执行准备页返回。

下层依赖：
- formation：完成当前编队识别、规则调整和单舰选船。
- support.supply、support.campaign_support、support.repair：完成准备页辅助流程。
- common.device.interaction、common.vision：提供页面状态识别和终态等待。

本文件只拥有准备页本身的 UI 原子动作和主流程顺序；OCR、规则规划、船池搜索、
补给和维修实现由对应子模块负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.main_page import constants
from autowsgr.application.ui.navigation.interaction import (
    NavigationError,
    click_and_wait_for_page,
    wait_leave_page,
)
from autowsgr.application.ui.navigation.types import PageName
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker, PageMatch, PixelChecker


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import numpy

    from autowsgr.application.ui.controller.context import UIContext
    from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import (
        FleetSnapshot,
    )
    from autowsgr.application.ui.controller.fleet.support.repair import RepairStrategy
    from autowsgr.application.ui.ships.types import ShipType
    from autowsgr.business.combat.fleet_models import FleetSlotRule
    from autowsgr.business.logistics.types import ShipDamageState
    from autowsgr.common.device.service import DeviceService


_log = get_logger('ui.fleet.main_page')


__all__ = ['BattlePreparationPage']


class BattlePreparationPage:
    """出征准备页控制器及其页面级主流程。"""

    # ── 准备页主流程 ────────────────────────────────────────────────────────

    def prepare_and_start_battle(
        self,
        *,
        fleet_id: int | None = None,
        fleet_rules: Sequence[FleetSlotRule] | None = None,
        task_type: str = 'normal',
        repair_strategy: RepairStrategy | None = None,
        repair_manually: bool | None = None,
        campaign_support_enabled: bool | None = None,
        recognize_ship_types: bool = True,
        target: str = 'combat',
    ) -> FleetSnapshot:
        """完成舰队准备、辅助处理并确认已经离开准备页。

        Args:
            fleet_id: 需要操作的舰队编号；为 None 时沿用当前舰队。
            fleet_rules: 已由业务入口规范化的编队规则；为 None 时不调整编队。
            task_type: 当前出征模式，用于选择准备页和编队调整路径。
            repair_strategy: 快速维修策略；为 None 时不执行快速维修。
            repair_manually: 是否在需要维修时中断给上层处理；为 None 时读取运行配置。
            campaign_support_enabled: 战役支援目标状态；为 None 时不操作战役支援。
            recognize_ship_types: 是否在编队识别中读取舰种。
            target: 出征离开准备页后用于日志和错误信息的目标名称。

        Returns:
            点击出征前最后一次确认的编队事实。

        Raises:
            RuntimeError: 编队规则无法满足或辅助流程无法完成。
            NavigationError: 当前不是准备页，或开始出征后仍停留在准备页。
        """
        screen = self._ctrl.screenshot()
        if not self.check_current_page(screen):
            raise NavigationError('当前页面不是出征准备页', screen=screen)

        snapshot = self.adjust_fleet(
            fleet_id=fleet_id,
            fleet_rules=fleet_rules,
            task_type=task_type,
            recognize_ship_types=recognize_ship_types,
        )
        self.apply_supply()
        if campaign_support_enabled is not None:
            self.ensure_campaign_support(enabled=campaign_support_enabled)
        if repair_strategy is not None:
            self.apply_repair(
                repair_strategy,
                repair_manually=repair_manually,
            )

        snapshot = self.read_fleet_snapshot(
            recognize_ship_types=recognize_ship_types,
        )
        if not self.try_start_battle(target=target):
            raise NavigationError(
                f'出征后仍停留在准备页: {target}',
                screen=self._ctrl.screenshot(),
            )
        return snapshot

    # ── 页面状态和基础操作 ──────────────────────────────────────────────────

    def __init__(self, ctx: UIContext) -> None:
        """保存调用方注入的运行上下文和设备控制器。"""
        self._ctx = ctx
        self._ctrl: DeviceService = ctx.ctrl

    # ── Fleet 子流程出口 ────────────────────────────────────────────────────

    def adjust_fleet(
        self,
        *,
        fleet_id: int | None,
        fleet_rules: Sequence[FleetSlotRule | str | None] | None,
        task_type: str = 'normal',
        reset_fleet: bool = True,
        recognize_ship_types: bool = True,
        on_event: Callable[..., None] | None = None,
    ) -> FleetSnapshot:
        """调用编队核心完成目标舰队调整。"""
        from autowsgr.application.ui.controller.fleet.formation import adjust_fleet

        return adjust_fleet(
            self._ctx,
            self,
            fleet_id=fleet_id,
            fleet_rules=fleet_rules,
            task_type=task_type,
            reset_fleet=reset_fleet,
            recognize_ship_types=recognize_ship_types,
            on_event=on_event,
        )

    def read_fleet_snapshot(
        self,
        *,
        expected_names: Sequence[str | None] | None = None,
        expected_pool: Sequence[str] | None = None,
        recognize_ship_types: bool = True,
    ) -> FleetSnapshot:
        """读取当前准备页的编队事实。"""
        from autowsgr.application.ui.controller.fleet.formation import read_fleet_snapshot

        return read_fleet_snapshot(
            self._ctx,
            expected_names=expected_names,
            expected_pool=expected_pool,
            recognize_ship_types=recognize_ship_types,
        )

    def read_ship_damage(self, screen: numpy.ndarray | None = None) -> dict[int, ShipDamageState]:
        """读取当前准备页六个舰船槽位的损伤状态。"""
        from autowsgr.application.ui.controller.fleet.support.repair import recognition

        if screen is None:
            screen = self._ctrl.screenshot()
        return recognition.detect_ship_damage(screen)

    def apply_supply(self, ship_ids: Sequence[int] | None = None) -> None:
        """调用补给辅助流程完成自动或快速补给。"""
        from autowsgr.application.ui.controller.fleet.support.supply import apply_supply

        apply_supply(self._ctx, self, ship_ids)

    def apply_repair(
        self,
        strategy: RepairStrategy | None = None,
        *,
        repair_manually: bool | None = None,
    ) -> list[int]:
        """调用维修辅助流程完成快速维修或上报手动维修需求。"""
        from autowsgr.application.ui.controller.fleet.support.repair import apply_repair

        return apply_repair(
            self._ctx,
            self,
            strategy,
            repair_manually=repair_manually,
        )

    def check_repair(self, strategy: RepairStrategy) -> list[int]:
        """调用维修辅助流程计算需要维修的物理槽位。"""
        from autowsgr.application.ui.controller.fleet.support.repair import check_repair

        return check_repair(self._ctx, strategy)

    def validate_campaign_fleet(
        self,
        required_types: Sequence[ShipType],
        *,
        validate_types: bool = True,
    ) -> bool:
        """调用编队核心校验战役舰种和数量限制。"""
        from autowsgr.application.ui.controller.fleet.formation import validate_campaign_fleet

        return validate_campaign_fleet(
            self._ctx,
            self,
            required_types,
            validate_types=validate_types,
        )

    @staticmethod
    def check_current_page(screen: numpy.ndarray) -> PageMatch:
        """判断截图是否为出征准备页面。"""
        result = ImageChecker.find_template(screen, Templates.Page.BATTLE_PREP, confidence=0.85)
        page_name = PageName.BATTLE_PREPARATION.value
        if result is None:
            return PageMatch(name=page_name, matched=False, score=0.0)
        return PageMatch(name=page_name, matched=True, score=result.confidence)

    @staticmethod
    def read_selected_fleet(screen: numpy.ndarray) -> int | None:
        """读取准备页当前选中的舰队编号。"""
        for fleet_id, (x, y) in constants.FLEET_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(constants.FLEET_ACTIVE, constants.STATE_TOLERANCE):
                return fleet_id
        return None

    @staticmethod
    def read_active_panel(screen: numpy.ndarray) -> constants.Panel | None:
        """读取准备页当前激活的底部面板。"""
        for panel, (x, y) in constants.PANEL_PROBE.items():
            pixel = PixelChecker.get_pixel(screen, x, y)
            if pixel.near(constants.PANEL_ACTIVE, constants.STATE_TOLERANCE):
                return panel
        return None

    def select_fleet(self, fleet: int) -> None:
        """点击指定舰队标签。"""
        if fleet not in constants.CLICK_FLEET:
            raise ValueError(f'舰队编号必须为 1-4，收到: {fleet}')
        _log.debug('[UI] 出征准备 -> 选择 {}队', fleet)
        self._ctrl.click(*constants.CLICK_FLEET[fleet])

    def select_panel(self, panel: constants.Panel) -> None:
        """点击指定底部面板标签。"""
        _log.debug('[UI] 出征准备 -> {}', panel.value)
        self._ctrl.click(*constants.CLICK_PANEL[panel])

    def click_ship_slot(self, slot: int) -> None:
        """点击准备页中的指定舰船槽位。"""
        if slot not in constants.CLICK_SHIP_SLOT:
            raise ValueError(f'舰船槽位必须为 0-5，收到: {slot}')
        _log.debug('[UI] 出征准备 -> 点击舰船位 {}', slot)
        self._ctrl.click(*constants.CLICK_SHIP_SLOT[slot])

    def start_battle(self) -> None:
        """点击开始出征按钮。"""
        _log.info('[UI] 出征准备 -> 开始出征')
        self._ctrl.click(*constants.CLICK_START_BATTLE)

    def try_start_battle(
        self,
        *,
        timeout: float = 1.5,
        target: str = 'combat',
    ) -> bool:
        """点击出征并确认已经离开准备页。"""
        self.start_battle()
        return (
            wait_leave_page(
                self._ctrl,
                checker=self.check_current_page,
                timeout=timeout,
                source=PageName.BATTLE_PREPARATION,
                target=target,
                probe=True,
            )
            is not None
        )

    def go_back(self) -> None:
        """点击回退按钮并确认已经返回 sortie 页面。"""
        from autowsgr.application.controller.sortie import SortiePage

        _log.debug('[UI] 出征准备 -> 回退')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=constants.CLICK_BACK,
            checker=SortiePage.check_current_page,
            source=PageName.BATTLE_PREPARATION,
            target=PageName.SORTIE_MAP,
        )

    def go_back_to_event(self) -> None:
        """点击回退按钮并确认已经返回活动地图页面。"""
        from autowsgr.application.ui.controller.home.event_page import BaseEventPage

        _log.debug('[UI] 出征准备 -> 返回活动地图')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=constants.CLICK_BACK,
            checker=BaseEventPage.check_current_page,
            source=PageName.BATTLE_PREPARATION,
            target=PageName.EVENT_MAP,
        )

    def ensure_campaign_support(self, *, enabled: bool = True) -> None:
        """确保当前准备页战役支援处于目标状态。"""
        from autowsgr.application.ui.controller.fleet.support.campaign_support import (
            apply_campaign_support,
        )

        apply_campaign_support(self._ctx, enabled=enabled)
