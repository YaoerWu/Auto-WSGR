"""模块功能：节点追踪的数据类型。

上层调用：
- application.combat.node_tracking.map_data：加载地图节点表。
- application.combat.node_tracking.algorithm：按候选节点算距离。
- application.combat.node_tracking.tracker：对外的节点追踪器。

边界：只定义数据结构；不读文件、不算距离。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NodePosition:
    """一个地图节点的位置信息。

    Attributes:
        name: 节点标识符，如 A、B。
        x: 节点横坐标（归一化 0.0-1.0）。
        y: 节点纵坐标（归一化 0.0-1.0）。
        next_nodes: 从该节点可以到达的下一批节点名。
    """

    name: str
    x: float
    y: float
    next_nodes: list[str] = field(default_factory=list)


__all__ = ['NodePosition']
