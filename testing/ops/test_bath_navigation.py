"""普通出征和决战进入澡堂的模式专用导航测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from autowsgr.application.errors import ManualRepairRequiredError
from autowsgr.application.ui.controller.fleet import (
    BattlePreparationPage,
    RepairStrategy,
)
from autowsgr.application.ui.controller.fleet.support.repair import workflow as repair_workflow
from autowsgr.application.navigation import service
from autowsgr.business.logistics.repair import bath_repair
from autowsgr.common.types import PageName, ShipDamageState


def test_normal_sortie_returns_to_map_before_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    """普通出征准备页先回普通地图，再进入澡堂。"""
    page = MagicMock()
    monkeypatch.setattr(
        'autowsgr.application.ui.controller.fleet.BattlePreparationPage',
        lambda _ctx: page,
    )
    goto_page = MagicMock()
    monkeypatch.setattr(service, 'goto_page', goto_page)
    ctx = object()

    service.goto_bath_from_normal_sortie(ctx)

    page.go_back.assert_called_once_with()
    goto_page.assert_called_once_with(ctx, PageName.BATH)


def test_event_sortie_returns_to_event_map_before_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    """活动出征准备页先回活动地图，再进入澡堂。"""
    page = MagicMock()
    monkeypatch.setattr(
        'autowsgr.application.ui.controller.fleet.BattlePreparationPage',
        lambda _ctx: page,
    )
    goto_page = MagicMock()
    monkeypatch.setattr(service, 'goto_page', goto_page)
    ctx = SimpleNamespace(ctrl=object())

    service.goto_bath_from_event_sortie(ctx)

    page.go_back_to_event.assert_called_once_with()
    goto_page.assert_called_once_with(ctx, PageName.BATH)


def test_campaign_sortie_returns_via_campaign_selection_before_bath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preparation = MagicMock()
    campaign_selection = MagicMock()
    monkeypatch.setattr(
        'autowsgr.application.ui.controller.fleet.BattlePreparationPage',
        lambda _ctx: preparation,
    )
    monkeypatch.setattr(
        'autowsgr.application.ui.controller.operations.sortie_page.main_page.SortiePage',
        lambda _ctx: campaign_selection,
    )
    goto_page = MagicMock()
    monkeypatch.setattr(service, 'goto_page', goto_page)
    ctx = object()

    service.goto_bath_from_campaign_sortie(ctx)

    preparation.go_back.assert_called_once_with()
    campaign_selection.go_back.assert_called_once_with()
    goto_page.assert_called_once_with(ctx, PageName.BATH)


def test_decisive_sortie_leaves_saved_map_before_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    """决战出征准备页使用暂离保存进度，回到总览后再进入澡堂。"""
    controller = MagicMock()
    decisive_config = object()
    ctx = SimpleNamespace(
        config=SimpleNamespace(decisive_battle=decisive_config),
        ctrl=object(),
    )
    monkeypatch.setattr(
        'autowsgr.application.ui.controller.operations.sortie_page.decisive_page.DecisiveMapController',
        lambda _ctx, _config: controller,
    )
    goto_page = MagicMock()
    monkeypatch.setattr(service, 'goto_page', goto_page)
    wait_for_page = MagicMock()
    monkeypatch.setattr('autowsgr.common.device.interaction.wait_for_page', wait_for_page)

    service.goto_bath_from_decisive_sortie(ctx)

    controller.navigate_to_map_page.assert_called_once_with()
    controller.open_retreat_dialog.assert_called_once_with()
    controller.confirm_leave.assert_called_once_with()
    controller.confirm_retreat.assert_not_called()
    wait_for_page.assert_called_once()
    assert wait_for_page.call_args.args[0] is ctx.ctrl
    assert wait_for_page.call_args.kwargs['target'] is PageName.DECISIVE_BATTLE
    goto_page.assert_called_once_with(ctx, PageName.BATH)


def test_manual_repair_action_runs_before_manual_repair_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = SimpleNamespace(
        ctrl=MagicMock(),
        config=SimpleNamespace(repair_manually=True),
        ocr=MagicMock(),
    )
    page = BattlePreparationPage(ctx)
    monkeypatch.setattr(repair_workflow, 'check_repair', lambda _ctx, _strategy: [0])

    with pytest.raises(ManualRepairRequiredError, match=r'\[0\]'):
        page.apply_repair(RepairStrategy.MODERATE)


def test_manual_bath_repair_dispatches_targets_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    page.repair.side_effect = [120, -1]
    page.repair.side_effect = [120, -1]
    ship = MagicMock()
    ctx = SimpleNamespace(
        bathroom=MagicMock(),
        config=SimpleNamespace(bathroom_count=2),
        get_ship=lambda _name: ship,
        update_ship_damage=MagicMock(),
    )
    goto_page = MagicMock()
    monkeypatch.setattr(bath_repair, 'BathPage', lambda _ctx: page)
    monkeypatch.setattr(bath_repair, 'goto_page', goto_page)

    dispatched = bath_repair.repair_manual_targets_in_bath(ctx, ['ship-1', 'ship-2'])

    page.repair.assert_any_call(repair_all=False, ship_name='ship-1')
    page.repair.assert_any_call(repair_all=False, ship_name='ship-2')
    ship.set_repair.assert_called_once_with(120)
    ctx.update_ship_damage.assert_called_once_with('ship-1', ShipDamageState.NORMAL)
    ctx.bathroom.occupy.assert_called_once_with(120)
    goto_page.assert_called_once_with(ctx, PageName.HOME)
    assert dispatched == ['ship-1']
