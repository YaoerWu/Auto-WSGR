"""模块功能：编排编队识别、规则调整、单舰选船和最终复查总流程。

上层调用：
- main_page.page：传入运行上下文、准备页控制器和规范化编队规则。

下层依赖：
- formation.fleet_recognition：读取当前编队事实。
- formation.fleet_adjustment：执行普通、战役和决战编队调整。
- common.fleet、common.types：提供编队规则和值类型。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.fleet_adjustment import (
    FleetAdjustment,
)
from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import recognition


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.ui.controller.context import UIContext
    from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import (
        FleetSnapshot,
    )
    from autowsgr.application.ui.controller.fleet.main_page import BattlePreparationPage
    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import ShipType
    from autowsgr.business.combat.fleet_models import FleetSlotRule


def adjust_fleet(
    ctx: UIContext,
    page: BattlePreparationPage,
    *,
    fleet_id: int | None,
    fleet_rules: Sequence[FleetSlotRule | str | None] | None,
    task_type: str = 'normal',
    reset_fleet: bool = True,
    recognize_ship_types: bool = True,
    on_event: Callable[..., None] | None = None,
) -> FleetSnapshot:
    """按规则完成一次编队调整并返回调整后的事实快照。"""
    if fleet_rules is None:
        if fleet_id is not None and page.read_selected_fleet(ctx.ctrl.screenshot()) != fleet_id:
            page.select_fleet(fleet_id)
        return read_fleet_snapshot(
            ctx,
            recognize_ship_types=recognize_ship_types,
        )
    adjustment = FleetAdjustment(
        ctx,
        page,
        use_search=task_type != 'decisive',
    )
    return adjustment.adjust_fleet(
        fleet_id,
        fleet_rules,
        task_type=task_type,
        reset_fleet=reset_fleet,
        recognize_ship_types=recognize_ship_types,
        on_event=on_event,
    )


def read_fleet_snapshot(
    ctx: UIContext,
    *,
    expected_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
    recognize_ship_types: bool = True,
) -> FleetSnapshot:
    """从准备页当前截图读取编队事实。"""
    if ctx.ocr is None:
        raise RuntimeError('编队识别需要 OCR 引擎')
    return recognition.read_fleet_snapshot(
        ctx.ctrl.screenshot(),
        ctx.ocr,
        expected_names=expected_names,
        expected_pool=expected_pool,
        recognize_ship_details=recognize_ship_types,
    )


def validate_campaign_fleet(
    ctx: UIContext,
    page: BattlePreparationPage,
    required_types: Sequence[ShipType],
    *,
    validate_types: bool = True,
) -> bool:
    """校验未配置具体舰名的战役当前编队。"""
    adjustment = FleetAdjustment(ctx, page)
    return adjustment.validate_campaign_fleet(
        required_types,
        validate_types=validate_types,
    )


__all__ = ['adjust_fleet', 'read_fleet_snapshot', 'validate_campaign_fleet']
