"""模块功能：舰船位置追踪与节点判定。

战斗移动阶段地图上有一个黄色小船图标沿航线移动，它就是舰队当前位置。这里把
每帧的小船坐标喂给算法层，得到当前所在节点；节点判定是后续决策的基础，不同
节点可以配置不同阵型、夜战策略和索敌规则。

上层调用：
- application.combat.engine.loop：地图路由阶段每轮更新船位与节点。

下层依赖：
- application.combat.node_tracking.map_data：节点坐标与后继。
- application.combat.node_tracking.algorithm：判节点。
- controller.sortie.battle_engine.tracking.checker：读小船像素位置、排除索敌页。

边界：只管一艘船在地图上的位置；不做战斗决策、不点按钮。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.combat.node_tracking.algorithm import select_node
from autowsgr.application.controller.sortie.battle_engine.tracking.checker import (
    read_ship_position_from_frame,
)
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    import numpy

    from autowsgr.application.combat.node_tracking.map_data import MapNodeData
    from autowsgr.application.combat.node_tracking.types import NodePosition

_log = get_logger('combat.tracker')


class NodeTracker:
    """舰船位置追踪与节点判定器。

    Args:
        map_data: 地图节点位置数据。
    """

    def __init__(self, map_data: MapNodeData) -> None:
        self._map_data = map_data
        self._ship_position: tuple[float, float] | None = None
        self._last_ship_position: tuple[float, float] | None = None
        self._current_node = '0'

    @property
    def current_node(self) -> str:
        """当前节点标识符。"""
        return self._current_node

    @property
    def ship_position(self) -> tuple[float, float] | None:
        """当前舰船位置（归一化），未检测到时为空。"""
        return self._ship_position

    def reset(self) -> None:
        """重置追踪状态，回到起始点。"""
        self._ship_position = None
        self._last_ship_position = None
        self._current_node = '0'

    def update_ship_position(self, frame: numpy.ndarray) -> tuple[float, float] | None:
        """在地图画面里定位黄色小船图标。

        Args:
            frame: 当前截图帧。

        Returns:
            小船归一化坐标；没找到、像素验证失败或当前是索敌页时为空。
        """
        center = read_ship_position_from_frame(frame)
        if center is None:
            _log.debug('[COMBAT] 未定位到小船（索敌页或像素验证失败）')
            return None
        self._ship_position = center
        _log.debug('[COMBAT] 船位更新：({:.3f}, {:.3f})', center[0], center[1])
        return center

    def update_node(self) -> str:
        """按当前船位判定所在节点。

        位置没变化就不重判；位置变了就在「当前节点 + 它的后继」里选，避免移动途中
        被强制前推。

        Returns:
            更新后的当前节点标识符。
        """
        if self._ship_position is None:
            return self._current_node
        if self._ship_position == self._last_ship_position:
            return self._current_node

        previous_position = self._last_ship_position
        self._last_ship_position = self._ship_position

        current_data = self._map_data.get(self._current_node)
        if current_data is None or not current_data.next_nodes:
            _log.warning('[COMBAT] 节点 {!r} 缺少路由信息，无法判定下一节点', self._current_node)
            return self._current_node

        candidates = self._candidates_of(current_data.next_nodes)
        self._log_candidates(candidates)
        next_node = select_node(
            current_node=self._current_node,
            ship_position=self._ship_position,
            previous_position=previous_position,
            candidates=candidates,
        )
        if next_node != self._current_node:
            _log.debug(
                '[COMBAT] 节点更新：{} → {}，船位=({:.3f}, {:.3f})',
                self._current_node,
                next_node,
                *self._ship_position,
            )
            self._current_node = next_node
        return self._current_node

    def track(self, frame: numpy.ndarray) -> str:
        """一站式追踪：更新船位再判节点。

        Args:
            frame: 当前截图帧。

        Returns:
            当前节点标识符。
        """
        self.update_ship_position(frame)
        return self.update_node()

    def _candidates_of(self, next_nodes: list[str]) -> list[NodePosition]:
        """拼出候选节点：当前节点本身加上它的后继，去重保序。"""
        names = list(dict.fromkeys([self._current_node, *next_nodes]))
        candidates = []
        for name in names:
            node = self._map_data.get(name)
            if node is not None:
                candidates.append(node)
        return candidates

    def _log_candidates(self, candidates: list[NodePosition]) -> None:
        """把候选节点坐标打进调试日志，方便对不上节点时排查。"""
        _log.debug(
            '[COMBAT] 当前节点 {}，候选：{}',
            self._current_node,
            '; '.join(f'{node.name}({node.x:.3f},{node.y:.3f})' for node in candidates),
        )


__all__ = ['NodeTracker']
