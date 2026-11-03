"""模块功能：验证出征准备页的单击落点与舰队编号校验。

直接调用方：项目测试运行器。

直接依赖：sortie.battle_preparation.page 与 conftest 的离屏上下文。

边界：只验证坐标与参数校验，不识别画面、不等待页面。
"""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.application.controller.sortie.battle_preparation import page as page_module
from autowsgr.application.controller.sortie.battle_preparation.page import BattlePreparationPage


@pytest.mark.parametrize('team', [1, 2, 3, 4])
def test_click_team_tab_clicks_matching_slot(ctx: Any, team: int) -> None:
    """第 N 队标签的落点就是坐标表里的第 N 项。"""
    BattlePreparationPage(ctx).click_team_tab(team)

    assert ctx.runtime.ctrl.clicks == [page_module.constants.CLICK_TEAM_TABS[team - 1]]


@pytest.mark.parametrize('team', [0, 5, -1])
def test_click_team_tab_rejects_out_of_range(ctx: Any, team: int) -> None:
    """舰队编号越界时在点击之前就报错。"""
    with pytest.raises(ValueError, match='舰队编号必须在 1 到 4 之间'):
        BattlePreparationPage(ctx).click_team_tab(team)

    assert ctx.runtime.ctrl.clicks == []


def test_go_back_clicks_back_button(ctx: Any) -> None:
    """返回只点一次校准好的返回圆环。"""
    BattlePreparationPage(ctx).go_back()

    assert ctx.runtime.ctrl.clicks == [page_module.constants.CLICK_BACK]
