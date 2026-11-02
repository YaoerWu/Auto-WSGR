"""模块功能：提供演习页检查器的模块入口。

上层调用：
- application.navigation：读取演习对手浮窗关闭、刷新、挑战三个按钮的落点。

下层依赖：
- exercise.checker：提供识别数据与识别入口。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.exercise.checker import (
    OVERLAY_CHALLENGE_ROI,
    OVERLAY_CHALLENGE_TEMPLATE,
    OVERLAY_CLOSE_ROI,
    OVERLAY_CLOSE_TEMPLATE,
    OVERLAY_REFRESH_ROI,
    OVERLAY_REFRESH_TEMPLATE,
    read_overlay_challenge_center,
    read_overlay_close_center,
    read_overlay_refresh_center,
)
from autowsgr.application.controller.sortie.exercise.page import ExercisePage


__all__ = [
    'OVERLAY_CHALLENGE_ROI',
    'OVERLAY_CHALLENGE_TEMPLATE',
    'OVERLAY_CLOSE_ROI',
    'OVERLAY_CLOSE_TEMPLATE',
    'OVERLAY_REFRESH_ROI',
    'OVERLAY_REFRESH_TEMPLATE',
    'ExercisePage',
    'read_overlay_challenge_center',
    'read_overlay_close_center',
    'read_overlay_refresh_center',
]
