"""模块功能：地图节点追踪的像素校准。

上层调用：
- controller.sortie.battle_engine.tracking.checker：找黄色簇、验小船图标像素。

下层依赖：
- 无。

边界：只保存颜色阈值与采样偏移；节点判定归 application.combat.node_tracking.algorithm。
"""

from __future__ import annotations


# ── 黄色簇（地图上的小船图标）──────────────────────────────────────────────

YELLOW_MIN_AREA = 200
"""黄色簇的最小像素面积；小于它的按零星噪点丢弃。"""

YELLOW_RED_MIN = 200
"""黄色簇的红色分量下限。"""

YELLOW_GREEN_MIN = 180
"""黄色簇的绿色分量下限。"""

YELLOW_BLUE_MIN = 50
"""黄色簇的蓝色分量下限。"""

YELLOW_BLUE_MAX = 150
"""黄色簇的蓝色分量上限。"""

SHIP_CENTER_COLOR = (239, 219, 106)
"""小船图标中心点的参考颜色（RGB）。"""

SHIP_SIDE_COLOR = (231, 222, 101)
"""小船图标左右两侧的参考颜色（RGB）。"""

SHIP_PIXEL_TOLERANCE = 40.0
"""小船图标三点采样的颜色容差。"""

SHIP_PIXEL_SIDE_OFFSET = 0.03
"""左右采样点相对中心点的横向偏移（归一化）。"""


__all__ = [
    'SHIP_CENTER_COLOR',
    'SHIP_PIXEL_SIDE_OFFSET',
    'SHIP_PIXEL_TOLERANCE',
    'SHIP_SIDE_COLOR',
    'YELLOW_BLUE_MAX',
    'YELLOW_BLUE_MIN',
    'YELLOW_GREEN_MIN',
    'YELLOW_MIN_AREA',
    'YELLOW_RED_MIN',
]
