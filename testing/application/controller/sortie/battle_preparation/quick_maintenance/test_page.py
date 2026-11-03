"""模块功能：验证快速整备面板三个按钮的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.battle_preparation.quick_maintenance.page 与共用离屏上下文。

边界：用共用离屏上下文记录点击，不识别画面、不访问设备。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance import (
    page as quick_module,
)
from autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.page import (
    QuickMaintenancePanel,
)


if TYPE_CHECKING:
    from typing import Any


def test_buttons_use_fallback_positions(ctx: Any, control: Any) -> None:
    """读不到识别中心时依次用三个固定落点。"""
    panel = QuickMaintenancePanel(ctx)
    panel.click_auto_supply()
    panel.click_quick_repair()
    panel.click_all_repair()

    assert control.clicks == [
        quick_module.CLICK_AUTO_SUPPLY,
        quick_module.CLICK_QUICK_REPAIR,
        quick_module.CLICK_ALL_REPAIR,
    ]


def test_buttons_prefer_recognized_center(ctx: Any, control: Any) -> None:
    """识别中心存在时优先用它，不再用固定落点。"""
    panel = QuickMaintenancePanel(ctx)
    panel.click_auto_supply((0.11, 0.12))
    panel.click_quick_repair((0.21, 0.22))
    panel.click_all_repair((0.31, 0.32))

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22), (0.31, 0.32)]
