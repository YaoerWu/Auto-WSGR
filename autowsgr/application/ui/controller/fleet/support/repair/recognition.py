"""模块功能：识别准备页六个舰船槽位的损伤状态。

上层调用：
- repair.workflow：根据损伤状态计算快速维修目标。

下层依赖：
- main_page.constants：提供准备页血条探测坐标。
- common.vision：执行像素读取和血量分类。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.main_page.constants import BLOOD_BAR_PROBE
from autowsgr.application.vision.damage_recognition import classify_blood
from autowsgr.common.vision import PixelChecker


if TYPE_CHECKING:
    import numpy

    from autowsgr.business.logistics.types import ShipDamageState


def detect_ship_damage(screen: numpy.ndarray) -> dict[int, ShipDamageState]:
    """读取六个物理槽位的满血、中破、大破或空槽状态。"""
    return {
        slot: classify_blood(PixelChecker.get_pixel(screen, *probe))
        for slot, probe in BLOOD_BAR_PROBE.items()
    }


__all__ = ['detect_ship_damage']
