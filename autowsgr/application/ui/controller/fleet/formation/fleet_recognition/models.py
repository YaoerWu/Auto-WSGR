"""模块功能：定义编队识别节点与调整节点之间共享的事实模型。

上层调用：
- formation.fleet_recognition.recognition：创建编队识别快照。
- formation.fleet_adjustment：读取槽位、舰名、舰种和等级事实。

下层依赖：
- common.types：提供舰种类型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import ShipType


@dataclass(slots=True)
class FleetSnapshot:
    """保存一次或多次截图合并得到的六个编队槽位事实。"""

    names: list[str | None]
    occupied: list[bool]
    ship_types: list[ShipType | None] | None = None
    ship_levels: list[int | None] | None = None

    @property
    def unknown_slots(self) -> list[int]:
        """返回已占用但尚未识别舰名的槽位。"""
        return [
            slot
            for slot, (name, occupied) in enumerate(zip(self.names, self.occupied, strict=True))
            if name is None and occupied
        ]

    @property
    def unknown_type_slots(self) -> list[int]:
        """返回已占用但尚未识别舰种的槽位。"""
        ship_types = self.ship_types or [None] * 6
        return [
            slot
            for slot, (ship_type, occupied) in enumerate(
                zip(ship_types, self.occupied, strict=True),
            )
            if ship_type is None and occupied
        ]

    @property
    def unknown_level_slots(self) -> list[int]:
        """返回已占用但尚未识别等级的槽位。"""
        ship_levels = self.ship_levels or [None] * 6
        return [
            slot
            for slot, (level, occupied) in enumerate(zip(ship_levels, self.occupied, strict=True))
            if level is None and occupied
        ]

    @property
    def has_unknown_details(self) -> bool:
        """返回是否仍有需要定点补识别的槽位字段。"""
        return bool(self.unknown_slots or self.unknown_type_slots or self.unknown_level_slots)
