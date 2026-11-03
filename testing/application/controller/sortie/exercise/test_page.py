"""模块功能：验证演习页选择对手与浮窗按钮的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.exercise.page 与共用离屏上下文。

边界：用共用离屏上下文记录滑动与点击，不识别画面、不访问设备。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie.exercise import page as exercise_module
from autowsgr.application.controller.sortie.exercise.page import ExercisePage


if TYPE_CHECKING:
    from typing import Any


def test_select_first_four_rivals_swipe_top(
    ctx: Any,
    control: Any,
) -> None:
    """对手 1-4 在首屏：先滑到顶，再点对应格位。"""
    page = ExercisePage(ctx)
    for rival_index in range(1, 5):
        page.select_rival(rival_index)

    assert control.swipes == [exercise_module._SWIPE_TO_TOP] * 4
    assert control.clicks == list(exercise_module._RIVAL_CHALLENGE_POSITIONS)


def test_select_fifth_rival_swipes_bottom(
    ctx: Any,
    control: Any,
) -> None:
    """对手 5 在列表末尾：滑到底后点首屏第四格。"""
    ExercisePage(ctx).select_rival(5)

    assert control.swipes == [exercise_module._SWIPE_TO_BOTTOM]
    assert control.clicks == [exercise_module._RIVAL_CHALLENGE_POSITIONS[3]]


@pytest.mark.parametrize('rival_index', [0, 6, -1])
def test_select_rival_rejects_out_of_range(
    ctx: Any,
    control: Any,
    rival_index: int,
) -> None:
    """序号超出 1-5 时先报错，不做任何滑动或点击。"""
    with pytest.raises(ValueError, match='演习对手序号必须是 1-5'):
        ExercisePage(ctx).select_rival(rival_index)

    assert control.swipes == []
    assert control.clicks == []


def test_overlay_buttons_use_fallback_positions(ctx: Any, control: Any) -> None:
    """读不到识别中心时用固定坐标兜底。"""
    page = ExercisePage(ctx)
    page.click_overlay_close()
    page.click_overlay_refresh()
    page.click_overlay_challenge()

    assert control.clicks == [
        exercise_module._CLICK_OVERLAY_CLOSE,
        exercise_module._CLICK_OVERLAY_REFRESH,
        exercise_module._CLICK_OVERLAY_CHALLENGE,
    ]


def test_overlay_buttons_prefer_recognized_center(ctx: Any, control: Any) -> None:
    """识别中心存在时优先用它，不再用固定坐标。"""
    page = ExercisePage(ctx)
    page.click_overlay_close((0.11, 0.12))
    page.click_overlay_refresh((0.21, 0.22))
    page.click_overlay_challenge((0.31, 0.32))

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22), (0.31, 0.32)]
