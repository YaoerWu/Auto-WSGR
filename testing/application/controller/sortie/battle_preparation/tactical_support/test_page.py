"""模块功能：验证战术支援点击控制器的落点契约。

直接调用方：项目测试运行器。
直接依赖：controller.sortie.battle_preparation.tactical_support.page。
边界：用替身接管设备点击，不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

from autowsgr.application.controller.sortie.battle_preparation.tactical_support import (
    TacticalSupportPage,
)
from autowsgr.application.controller.sortie.battle_preparation.tactical_support import (
    constants as tactical_constants,
)


def _make_page(clicks: list[tuple[float, float]]) -> TacticalSupportPage:
    """用只记录落点的假控制器组装页面门面。"""
    ctx = SimpleNamespace(
        runtime=SimpleNamespace(ctrl=SimpleNamespace(click=lambda x, y: clicks.append((x, y))))
    )
    return TacticalSupportPage(ctx)  # type: ignore[arg-type]


def test_support_button_falls_back_to_calibrated_center() -> None:
    """不传落点时用校准坐标，点开浮窗这一步不必先识别。"""
    clicks: list[tuple[float, float]] = []
    page = _make_page(clicks)

    page.click_support_button()

    assert clicks == [tactical_constants.CLICK_SUPPORT_BUTTON]


def test_support_button_prefers_measured_center() -> None:
    """识别到按钮中心时优先用实测落点。"""
    clicks: list[tuple[float, float]] = []
    page = _make_page(clicks)

    page.click_support_button((0.7, 0.2))

    assert clicks == [(0.7, 0.2)]


def test_toggle_button_falls_back_to_calibrated_center() -> None:
    """开关按钮的落点不随开关文案变化，静态兜底即可。"""
    clicks: list[tuple[float, float]] = []
    page = _make_page(clicks)

    page.click_toggle_button()
    page.click_toggle_button((0.75, 0.5))

    assert clicks == [tactical_constants.CLICK_TOGGLE_BUTTON, (0.75, 0.5)]
