"""验证战役页面识别、查询和出征入口的无设备单元测试。

上层调用：
- testing：执行战役页面控制器回归测试。

下层依赖：
- application.ui.controller.operations.sortie_page.campaign_page：提供战役页面入口。

边界：
只验证战役页面自身的流程和识别契约，不连接设备或适配外部业务调用。
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from autowsgr.application.controller.sortie import SortieTab
from autowsgr.application.ui.controller.operations.sortie_page.campaign_page import (
    CampaignPage,
    constants,
    recognition,
)
from autowsgr.application.ui.controller.operations.sortie_page.campaign_page import (
    page as page_module,
)
from autowsgr.common.types import PageName


def test_recognize_difficulty_reads_hard_indicator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """难度识别使用难度按钮探测坐标和颜色事实。"""
    pixel = MagicMock()
    pixel.near.side_effect = [True]
    get_pixel = MagicMock(return_value=pixel)
    monkeypatch.setattr(recognition.PixelChecker, 'get_pixel', get_pixel)

    screen = object()

    assert recognition.recognize_difficulty(screen) == 'hard'
    get_pixel.assert_called_once_with(screen, *constants.CLICK_DIFFICULTY)


def test_campaign_page_exposes_only_complete_entry_contract() -> None:
    """页面不暴露仅用于查询的中间方法。"""
    assert not hasattr(CampaignPage, 'read_campaign_remains')
    assert not hasattr(CampaignPage, 'read_acquisition_counts')
    assert not hasattr(CampaignPage, 'read_difficulty')


def test_recognize_campaign_remains_reads_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """战役次数识别从 OCR 文本读取剩余次数和总次数。"""
    screen = object()
    cropped = object()
    ocr_engine = MagicMock()
    ocr_engine.recognize.return_value = [SimpleNamespace(text='2/5')]
    crop = MagicMock(return_value=cropped)
    monkeypatch.setattr(recognition.PixelChecker, 'crop', crop)

    assert recognition.recognize_campaign_remains(screen, ocr_engine) == (2, 5)

    crop.assert_called_once()
    ocr_engine.recognize.assert_called_once_with(cropped)


def test_recognize_acquisition_counts_returns_recognized_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """出征统计识别返回舰船和战利品数量。"""
    ocr_engine = MagicMock()
    monkeypatch.setattr(recognition, 'recognize_loot_count', lambda *_args: 4)
    monkeypatch.setattr(recognition, 'recognize_ship_count', lambda *_args: 3)

    result = recognition.recognize_acquisition_counts(object(), ocr_engine)

    assert result.ship_count == 3
    assert result.loot_count == 4


def test_enter_campaign_owns_the_complete_entry_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """战役入口按标签、难度、战役和目标页面顺序执行。"""
    ctrl = MagicMock()
    ctx = SimpleNamespace(ctrl=ctrl, ocr=MagicMock())
    page = CampaignPage(ctx)
    select_tab = MagicMock()
    recognize = MagicMock(side_effect=['easy', 'hard'])
    wait_for_page = MagicMock()
    page.select_tab = select_tab
    ctrl.screenshot.return_value = object()
    monkeypatch.setattr(page_module.recognition, 'recognize_difficulty', recognize)
    monkeypatch.setattr(page_module.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(page_module, 'wait_for_page', wait_for_page)

    fleet_module = ModuleType('autowsgr.application.ui.controller.fleet')

    class FakeBattlePreparationPage:
        @staticmethod
        def check_current_page(_screen: object) -> bool:
            return True

    fleet_module.BattlePreparationPage = FakeBattlePreparationPage
    monkeypatch.setitem(
        sys.modules,
        'autowsgr.application.ui.controller.fleet',
        fleet_module,
    )

    page.enter_campaign(
        map_index=2,
        difficulty='hard',
        campaign_name='困难潜艇',
    )

    select_tab.assert_called_once_with(SortieTab.CAMPAIGN)
    assert ctrl.click.call_args_list == [
        call(*constants.CLICK_DIFFICULTY),
        call(*constants.CAMPAIGN_POSITIONS[2]),
    ]
    assert recognize.call_count == 2
    wait_for_page.assert_called_once_with(
        ctrl,
        checker=FakeBattlePreparationPage.check_current_page,
        source='战役页面-困难潜艇',
        target=PageName.BATTLE_PREPARATION.value,
    )


def test_enter_campaign_rejects_invalid_arguments() -> None:
    """战役入口拒绝超出页面约束的编号和难度。"""
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock())
    page = CampaignPage(ctx)

    with pytest.raises(ValueError, match='战役编号'):
        page.enter_campaign(map_index=0)
    with pytest.raises(ValueError, match='难度'):
        page.enter_campaign(difficulty='normal')
