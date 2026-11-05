"""模块功能：节点追踪的算法层。

在若干候选节点里挑出舰队当前最可能所在的节点。全部是纯函数，输入坐标、输出
节点名，不带任何追踪器状态。

上层调用：
- application.combat.node_tracking.tracker：把算法结果存进追踪状态。

上层依赖：
- application.combat.node_tracking.constants：射线命中阈值。

边界：不读地图文件、不读像素、不记状态、不点按钮。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from autowsgr.application.combat.node_tracking.constants import RAY_HIT_THRESHOLD


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.combat.node_tracking.types import NodePosition


def select_node(
    *,
    current_node: str,
    ship_position: tuple[float, float],
    previous_position: tuple[float, float] | None,
    candidates: Sequence[NodePosition],
) -> str:
    """在候选节点里挑出舰队当前最可能所在的节点。

    有速度方向时优先按「到这条航线的距离」判，射线命中阈值的节点里再按欧氏距离
    打破平局；没有速度方向（首帧）时退化为纯欧氏距离。

    Args:
        current_node: 当前节点名，全部候选都没判出来时原样返回。
        ship_position: 小船当前的归一化坐标。
        previous_position: 上一帧的小船坐标，用于算速度方向。
        candidates: 候选节点，至少包含当前节点与它的后继。

    Returns:
        判定出的节点名。
    """
    direction_x, direction_y = _velocity_direction(ship_position, previous_position)
    has_direction = (direction_x * direction_x + direction_y * direction_y) > 1e-12

    metrics: list[tuple[str, float, float]] = []
    for node in candidates:
        euclidean = euclidean_distance(ship_position[0], ship_position[1], node.x, node.y)
        ray = (
            point_to_ray_distance(
                node.x,
                node.y,
                ship_position[0],
                ship_position[1],
                direction_x,
                direction_y,
            )
            if has_direction
            else euclidean
        )
        metrics.append((node.name, ray, euclidean))

    if not metrics:
        return current_node

    hits = [item for item in metrics if item[1] < RAY_HIT_THRESHOLD]
    if hits:
        return min(hits, key=lambda item: (item[2], item[1]))[0]
    return min(metrics, key=lambda item: (item[1], item[2]))[0]


def euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """计算两点间欧几里得距离。

    Args:
        x1: 第一个点的横坐标。
        y1: 第一个点的纵坐标。
        x2: 第二个点的横坐标。
        y2: 第二个点的纵坐标。

    Returns:
        两点距离。
    """
    return math.hypot(x1 - x2, y1 - y2)


def point_to_ray_distance(
    point_x: float,
    point_y: float,
    origin_x: float,
    origin_y: float,
    direction_x: float,
    direction_y: float,
) -> float:
    """计算点到射线的最小距离。

    射线由起点和方向向量定义；点落在射线反向半平面时，退化为到起点的距离。

    Args:
        point_x: 点的横坐标。
        point_y: 点的纵坐标。
        origin_x: 射线起点横坐标。
        origin_y: 射线起点纵坐标。
        direction_x: 射线方向向量横分量。
        direction_y: 射线方向向量纵分量。

    Returns:
        点到射线的最小距离。
    """
    vector_x = point_x - origin_x
    vector_y = point_y - origin_y
    if vector_x * direction_x + vector_y * direction_y <= 0:
        return math.hypot(vector_x, vector_y)
    direction_length = math.hypot(direction_x, direction_y)
    if direction_length == 0:
        return math.hypot(vector_x, vector_y)
    cross = abs(vector_x * direction_y - vector_y * direction_x)
    return cross / direction_length


def _velocity_direction(
    ship_position: tuple[float, float],
    previous_position: tuple[float, float] | None,
) -> tuple[float, float]:
    """算上一帧到当前帧的方向向量，缺上一帧时返回零向量。"""
    if previous_position is None:
        return 0.0, 0.0
    return ship_position[0] - previous_position[0], ship_position[1] - previous_position[1]


__all__ = [
    'euclidean_distance',
    'point_to_ray_distance',
    'select_node',
]
