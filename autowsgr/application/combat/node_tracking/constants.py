"""模块功能：节点追踪的静态校准数据。

上层调用：
- application.combat.node_tracking.map_data：地图数据根目录与入口映射。
- application.combat.node_tracking.algorithm：射线命中阈值。

边界：只放不容易变的路径与判定容差；像素阈值归 controller 的 tracking checker。
"""

from __future__ import annotations

from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parents[4] / 'resources' / 'data'
"""仓库根目录下的资源数据根。"""

MAP_DATA_ROOT = DATA_ROOT / 'map' / 'normal'
"""常规战地图节点数据目录。"""

EVENT_MAP_DATA_ROOT = DATA_ROOT / 'map' / 'event'
"""活动地图节点数据目录。"""

ENTRANCE_TO_GREEK = {'a': 'α', 'b': 'β'}
"""活动入口标识 a/b 到地图文件名希腊字母的映射。"""

START_NODE_REMAP = {'α': '0', 'β': '0'}
"""活动入口节点到起始点的映射。

每个活动地图文件只有一个入口点（由文件名后缀 α/β 决定），加载时统一映射为 0，
与常规战起始点一致，追踪器初始节点 0 即可直接匹配。
"""

RAY_HIT_THRESHOLD = 0.01
"""节点判定的射线距离阈值，命中即认为船在这条航线上。"""

__all__ = [
    'DATA_ROOT',
    'ENTRANCE_TO_GREEK',
    'EVENT_MAP_DATA_ROOT',
    'MAP_DATA_ROOT',
    'RAY_HIT_THRESHOLD',
    'START_NODE_REMAP',
]
