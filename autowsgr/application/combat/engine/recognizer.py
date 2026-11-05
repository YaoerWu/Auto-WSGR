"""模块功能：战斗阶段的单帧识别与等待。

上层调用：
- application.combat.engine.loop：推进流程前问一句现在是什么阶段。
- application.combat.engine.handlers：结算页点继续时轮询下一阶段。

下层依赖：
- controller.sortie.battle_engine.monitor.checker：单帧阶段判定。
- controller.sortie.battle_engine.monitor.constants：各阶段的超时与命中后等待。
- common.vision：截图。

边界：只回答当前画面属于哪个阶段；不点击、不推进流程、不写历史。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.combat.errors import (
    CombatRecognitionTimeoutError,
    CombatStopRequestedError,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    read_phase_from_frame,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.constants import (
    PHASE_SIGNATURES,
    PhaseSignature,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import screenshot


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import numpy

    from autowsgr.application.combat.engine.types import CombatPhase
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


class CombatRecognizer:
    """战斗阶段识别器。

    一次截图匹配全部候选阶段，命中即返回；等待窗口取候选里最长的超时。

    Args:
        ctx: 上下文句柄，提供设备截图。
        stop_requested: 可选的停止询问函数，返回真即中断等待。
    """

    def __init__(
        self,
        ctx: ContextHandle,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        self._ctx = ctx
        self._stop_requested = stop_requested or (lambda: False)

    def wait_for_phase(
        self,
        candidates: Sequence[CombatPhase],
        *,
        poll_action: Callable[[numpy.ndarray], None] | None = None,
    ) -> CombatPhase:
        """等待候选阶段之一出现。

        Args:
            candidates: 候选阶段，按优先级排列。
            poll_action: 每轮匹配前执行的动作，拿得到当前帧（如点击加速、
                更新节点位置）。

        Returns:
            命中的阶段。

        Raises:
            CombatStopRequestedError: 外部要求停止。
            CombatRecognitionTimeoutError: 所有候选都没在超时内出现。
        """
        timeout = max(_signature_of(phase).timeout_seconds for phase in candidates)
        deadline = time.monotonic() + timeout
        _log.debug(
            '[COMBAT] 等待阶段 → 候选={}：超时={:.1f}s',
            [phase.name for phase in candidates],
            timeout,
        )

        while time.monotonic() < deadline:
            if self._stop_requested():
                raise CombatStopRequestedError('任务被用户停止')

            # 轮询节奏由截图本身决定，不再额外等待，与旧实现保持一致。
            frame = screenshot(self._ctx)
            if poll_action is not None:
                poll_action(frame)

            phase = read_phase_from_frame(frame, candidates)
            if phase is None:
                continue

            signature = _signature_of(phase)
            if signature.after_match_delay > 0:
                time.sleep(signature.after_match_delay)
            _log.debug('[COMBAT] 命中阶段 → {}', phase.name)
            return phase

        names = [phase.name for phase in candidates]
        raise CombatRecognitionTimeoutError(f'等待状态超时 ({timeout:.1f}s): {names}')

    def identify_current(
        self,
        frame: numpy.ndarray,
        candidates: Sequence[CombatPhase],
    ) -> CombatPhase | None:
        """在给定帧上识别当前阶段，不等待、不再截图。"""
        return read_phase_from_frame(frame, candidates)


def _signature_of(phase: CombatPhase) -> PhaseSignature:
    """取阶段的视觉判据；未登记的阶段按纯等待处理。"""
    return PHASE_SIGNATURES.get(phase, PhaseSignature())


__all__ = ['CombatRecognizer']
