"""模块功能：地图节点追踪子包。

上层调用：
- application.combat.engine.loop：地图模式下加载地图、每轮更新节点。

边界：对外只暴露地图数据与追踪器；算法与常量属于内部实现。
"""

from autowsgr.application.combat.node_tracking.map_data import MapNodeData
from autowsgr.application.combat.node_tracking.tracker import NodeTracker
from autowsgr.application.combat.node_tracking.types import NodePosition


__all__ = [
    'MapNodeData',
    'NodePosition',
    'NodeTracker',
]
