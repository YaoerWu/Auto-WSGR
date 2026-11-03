"""模块功能：控制演习页的选择对手与对手详情浮窗按钮。

上层调用：
- application.navigation：执行演习页与对手详情浮窗之间的页面边动作。

下层依赖：
- autowsgr.application.controller.sortie.exercise.constants：提供滑动与点击落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行滑动与点击。
- common.system.logger：记录实际落点。
- 标准库 time：等待列表惯性滚动停下。

边界：只点已定位的位置，不识别画面、不等待页面、不判断到达、不编排业务。
浮窗按钮的落点由导航器读模板中心后传入，读不到时用固定坐标兜底。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.exercise import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.sortie.exercise')


# 列表滑动要等惯性滚动停下，否则后续点击会落在滚动途中的位置。
_SWIPE_SETTLE_SECONDS = 0.8


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class ExercisePage:
    """演习页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 选择对手 ────────────────────────────────────────────────────────────

    def select_rival(self, rival_index: int) -> None:
        """定位指定对手，点开它的对手详情浮窗。

        前四个对手在首屏，第五个要滑到底。滑动对当前停在哪一屏都成立，所以直接滑。

        Args:
            rival_index: 对手序号，范围 1-5。

        Raises:
            ValueError: 对手序号不在 1-5 范围内。
        """
        if not 1 <= rival_index <= 5:
            raise ValueError(f'演习对手序号必须是 1-5，收到 {rival_index!r}')

        ctrl = self._ctx.runtime.ctrl
        if rival_index <= constants.VISIBLE_RIVAL_SLOTS:
            ctrl.swipe(*constants.SWIPE_TO_TOP)
            visible_slot = rival_index - 1
        else:
            ctrl.swipe(*constants.SWIPE_TO_BOTTOM)
            visible_slot = constants.VISIBLE_RIVAL_SLOTS - 1
        time.sleep(_SWIPE_SETTLE_SECONDS)
        _log.debug(
            '[UI] 演习页 → 选择对手：rival={}，visible_slot={}',
            rival_index,
            visible_slot,
        )
        ctrl.click(*constants.RIVAL_CHALLENGE_POSITIONS[visible_slot])

    # ── 对手详情浮窗 ────────────────────────────────────────────────────────

    def click_overlay_close(self, position: tuple[float, float] | None = None) -> None:
        """关闭对手详情浮窗，回到演习页。

        Args:
            position: 导航器从关闭按钮模板读到的中心；为空时用固定坐标兜底。
        """
        self._click_overlay_button(position, constants.CLICK_OVERLAY_CLOSE)

    def click_overlay_refresh(self, position: tuple[float, float] | None = None) -> None:
        """刷新当前对手的阵容。

        Args:
            position: 导航器从刷新按钮模板读到的中心；为空时用固定坐标兜底。
        """
        self._click_overlay_button(position, constants.CLICK_OVERLAY_REFRESH)

    def click_overlay_challenge(self, position: tuple[float, float] | None = None) -> None:
        """点浮窗里的挑战按钮，进入演习准备页。

        Args:
            position: 导航器从挑战按钮模板读到的中心；为空时用固定坐标兜底。
        """
        self._click_overlay_button(position, constants.CLICK_OVERLAY_CHALLENGE)

    # ── 私有辅助 ────────────────────────────────────────────────────────────

    def _click_overlay_button(
        self,
        position: tuple[float, float] | None,
        fallback: tuple[float, float],
    ) -> None:
        """点浮窗按钮，优先用识别中心。"""
        landing = position if position is not None else fallback
        self._ctx.runtime.ctrl.click(*landing)


__all__ = [
    'ExercisePage',
]
