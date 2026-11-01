"""模块功能：验证演习页控制器的对手定位与浮窗按钮落点。

上层调用：
- pytest：执行演习页控制器的无设备单元检查。

下层依赖：
- application.ui.controller.sortie.exercise：提供页面控制器。

边界：
本模块只使用 mock 控制器验证落点选择，不连接真实设备、不读写识别结果。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from autowsgr.application.ui.controller.sortie.exercise import ExercisePage
from autowsgr.application.ui.controller.sortie.exercise import page as page_module


def _make_page(monkeypatch: pytest.MonkeyPatch) -> tuple[ExercisePage, MagicMock]:
    """创建绑定 mock 控制器的演习页，并跳过滑动后的等待。"""
    monkeypatch.setattr(page_module, 'time', SimpleNamespace(sleep=lambda _seconds: None))
    ctrl = MagicMock()
    ctx = SimpleNamespace(runtime=SimpleNamespace(ctrl=ctrl))
    return ExercisePage(ctx), ctrl


def test_select_first_rival_slides_to_top_and_clicks_first_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """选前四个对手时先把列表滑到顶部，再点多出来的那一格。"""
    page, ctrl = _make_page(monkeypatch)

    page.select_rival(2)

    ctrl.swipe.assert_called_once_with(*page_module._SWIPE_TO_TOP)
    ctrl.click.assert_called_once_with(*page_module._RIVAL_CHALLENGE_POSITIONS[1])


def test_select_fifth_rival_slides_to_bottom_and_clicks_last_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第五个对手在列表底部，滑到底后落在第四格。"""
    page, ctrl = _make_page(monkeypatch)

    page.select_rival(5)

    ctrl.swipe.assert_called_once_with(*page_module._SWIPE_TO_BOTTOM)
    ctrl.click.assert_called_once_with(*page_module._RIVAL_CHALLENGE_POSITIONS[3])


@pytest.mark.parametrize('rival_index', [0, 6, -1])
def test_select_rival_rejects_index_out_of_range(
    rival_index: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """序号越界在任何设备动作前被拒绝。"""
    page, ctrl = _make_page(monkeypatch)

    with pytest.raises(ValueError, match='1-5'):
        page.select_rival(rival_index)

    ctrl.swipe.assert_not_called()
    ctrl.click.assert_not_called()


def test_overlay_buttons_prefer_detected_center(monkeypatch: pytest.MonkeyPatch) -> None:
    """导航器传进来的模板中心优先于固定兜底坐标。"""
    page, ctrl = _make_page(monkeypatch)

    page.click_overlay_close((0.1, 0.2))
    page.click_overlay_refresh((0.3, 0.4))
    page.click_overlay_challenge((0.5, 0.6))

    assert [call.args for call in ctrl.click.call_args_list] == [
        (0.1, 0.2),
        (0.3, 0.4),
        (0.5, 0.6),
    ]


def test_overlay_buttons_fall_back_to_fixed_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """读不到模板中心时退回固定落点，不会连点空坐标。"""
    page, ctrl = _make_page(monkeypatch)

    page.click_overlay_close()
    page.click_overlay_refresh()
    page.click_overlay_challenge()

    assert [call.args for call in ctrl.click.call_args_list] == [
        page_module._CLICK_OVERLAY_CLOSE,
        page_module._CLICK_OVERLAY_REFRESH,
        page_module._CLICK_OVERLAY_CHALLENGE,
    ]
