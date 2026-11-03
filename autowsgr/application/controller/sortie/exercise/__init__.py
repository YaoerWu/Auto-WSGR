"""模块功能：提供演习页检查器的模块入口。

上层调用：
- application.navigation：读取演习对手浮窗关闭、刷新、挑战三个按钮的落点。
- application.fleet_select：读取浮窗上六个对手的舰种与等级。

下层依赖：
- exercise.checker：提供识别入口。
- exercise.constants：提供识别数据。
- exercise.page：提供演习页点击操作。

本模块只导出稳定入口，不放业务实现。
"""

from autowsgr.application.controller.sortie.exercise.checker import (
    RivalShip,
    read_overlay_challenge_center,
    read_overlay_close_center,
    read_overlay_refresh_center,
    read_rival_ships,
)
from autowsgr.application.controller.sortie.exercise.constants import (
    EXERCISE_RIVAL_SLOTS,
    OVERLAY_CHALLENGE_ROI,
    OVERLAY_CHALLENGE_TEMPLATE,
    OVERLAY_CLOSE_ROI,
    OVERLAY_CLOSE_TEMPLATE,
    OVERLAY_REFRESH_ROI,
    OVERLAY_REFRESH_TEMPLATE,
    RIVAL_SHIP_LEVEL_ROIS,
    RIVAL_SHIP_TYPE_ROIS,
)
from autowsgr.application.controller.sortie.exercise.page import ExercisePage


__all__ = [
    'EXERCISE_RIVAL_SLOTS',
    'OVERLAY_CHALLENGE_ROI',
    'OVERLAY_CHALLENGE_TEMPLATE',
    'OVERLAY_CLOSE_ROI',
    'OVERLAY_CLOSE_TEMPLATE',
    'OVERLAY_REFRESH_ROI',
    'OVERLAY_REFRESH_TEMPLATE',
    'RIVAL_SHIP_LEVEL_ROIS',
    'RIVAL_SHIP_TYPE_ROIS',
    'ExercisePage',
    'RivalShip',
    'read_overlay_challenge_center',
    'read_overlay_close_center',
    'read_overlay_refresh_center',
    'read_rival_ships',
]
