"""模块功能：地图节点数据的加载与查询。

一张地图对应一个 YAML 文件，每项是一个节点的归一化坐标和可达节点。常规战从
resources/data/map/normal/{chapter}-{map_id}.yaml 读，活动战从
resources/data/map/event/{活动名}/ 下读。

上层调用：
- application.combat.node_tracking.tracker：按节点名查坐标与后继。
- application.combat.engine.loop：开局按作战模式加载地图。

边界：只负责把 YAML 变成节点表；不追踪船、不判节点。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.combat.node_tracking.constants import (
    ENTRANCE_TO_GREEK,
    EVENT_MAP_DATA_ROOT,
    MAP_DATA_ROOT,
    START_NODE_REMAP,
)
from autowsgr.application.combat.node_tracking.types import NodePosition
from autowsgr.common.system.files import load_yaml
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from pathlib import Path


_log = get_logger('combat.tracker')


class MapNodeData:
    """单个地图的节点位置数据。

    节点坐标是归一化形式。地图格式示例：

    "0":
      position: [0.208, 0.648]
      next: ["A"]
    A:
      position: [0.295, 0.522]
      next: ["B", "C"]
    """

    def __init__(self, nodes: dict[str, NodePosition]) -> None:
        """保存已解析的节点表。

        Args:
            nodes: 节点名到位置信息的映射。
        """
        self._nodes = nodes

    @property
    def node_names(self) -> list[str]:
        """所有节点名（排除起始点 0）。"""
        return [name for name in self._nodes if name != '0']

    def get(self, name: str) -> NodePosition | None:
        """按名称获取节点。

        Args:
            name: 节点标识符。

        Returns:
            节点位置信息，不存在时为空。
        """
        return self._nodes.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    @classmethod
    def load(cls, chapter: int | str, map_id: int | str) -> MapNodeData | None:
        """从 YAML 文件加载常规地图节点数据。

        Args:
            chapter: 章节号。
            map_id: 地图号。

        Returns:
            节点表；文件不存在时为空。
        """
        path = MAP_DATA_ROOT / f'{chapter}-{map_id}.yaml'
        if not path.exists():
            _log.warning('[COMBAT] 地图文件不存在：{}', path)
            return None
        raw: dict[str, Any] = load_yaml(path, allowed_root=MAP_DATA_ROOT.parent)
        return cls._parse(raw)

    @classmethod
    def load_event(
        cls,
        event_name: str,
        chapter: int | str,
        map_id: int | str,
        entrance: str | None = None,
    ) -> MapNodeData | None:
        """从 YAML 文件加载活动地图节点数据。

        支持两种命名：旧活动用 {chapter}-{map_id}.yaml；新活动用中文前缀加
        {H?}-Ex-{map_id}-{α|β}.yaml，见 _resolve_event_map_path。

        Args:
            event_name: 活动名称，如 20260730。
            chapter: 活动难度档，如 H、E。
            map_id: 地图编号。
            entrance: 活动入口 a（α）、b（β）或空。新活动必填。

        Returns:
            节点表；文件不存在或匹配歧义时为空。
        """
        path = _resolve_event_map_path(EVENT_MAP_DATA_ROOT, event_name, chapter, map_id, entrance)
        if path is None or not path.exists():
            _log.warning(
                '[COMBAT] 活动地图文件不存在：{}/{}-{}（entrance={}）',
                event_name,
                chapter,
                map_id,
                entrance,
            )
            return None
        raw: dict[str, Any] = load_yaml(path, allowed_root=EVENT_MAP_DATA_ROOT)
        _log.debug('[COMBAT] 加载活动地图数据：{}', path)
        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> MapNodeData:
        """把 YAML 原始数据解析成节点表。

        Args:
            raw: YAML 读出的映射。

        Returns:
            解析好的节点表。
        """
        nodes: dict[str, NodePosition] = {}
        for key, value in raw.items():
            name = START_NODE_REMAP.get(str(key), str(key))
            if not isinstance(value, dict):
                _log.warning("[COMBAT] 忽略无法解析的节点 '{}'：{}", name, value)
                continue
            position = value.get('position', [0, 0])
            raw_next = value.get('next', [])
            nodes[name] = NodePosition(
                name=name,
                x=position[0],
                y=position[1],
                next_nodes=[
                    START_NODE_REMAP.get(str(next_name), str(next_name)) for next_name in raw_next
                ],
            )
        _log.debug('[COMBAT] 加载 {} 个节点：{}', len(nodes), list(nodes))
        return cls(nodes)


def _resolve_event_map_path(
    event_root: Path,
    event_name: str,
    chapter: int | str,
    map_id: int | str,
    entrance: str | None,
) -> Path | None:
    """解析活动地图文件路径。

    entrance 为空时用旧命名 {chapter}-{map_id}.yaml；为 a、b 时用新活动中文命名
    {中文前缀}{H?}-Ex-{map_id}-{α|β}.yaml，用通配符匹配中文前缀，不硬编码活动名。

    Args:
        event_root: 活动地图根目录。
        event_name: 活动名称。
        chapter: 活动难度档。
        map_id: 地图编号。
        entrance: 活动入口标识。

    Returns:
        唯一匹配的路径；零个或多个匹配时为空。
    """
    event_dir = event_root / event_name
    if entrance is None:
        return event_dir / f'{chapter}-{map_id}.yaml'

    greek = ENTRANCE_TO_GREEK.get(entrance)
    if greek is None:
        _log.warning('[COMBAT] 未知入口标识 {!r}，应为 a/b', entrance)
        return None

    difficulty = str(chapter).upper()
    hard_prefix = 'H' if difficulty == 'H' else ''
    matches = sorted(event_dir.glob(f'*{hard_prefix}-Ex-{map_id}-{greek}.yaml'))
    if difficulty != 'H':
        matches = [path for path in matches if 'H-Ex' not in path.stem]
    if not matches:
        return None
    if len(matches) > 1:
        _log.warning('[COMBAT] 活动地图文件匹配歧义（{} 个）：{}', len(matches), matches)
        return None
    return matches[0]


__all__ = ['MapNodeData']
