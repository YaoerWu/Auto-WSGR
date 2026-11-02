"""模块功能：定义船只识别各域共用的事实模型。

上层调用：
- application.controller.sortie.battle_preparation.ship_recognition.service：把各域识别结果作为统一出口返回。
- application.controller.sortie.battle_preparation.ship_recognition.models 下的各识别域：产出并填充槽位事实。

下层依赖：
- application.controller.types：提供舰种枚举。

边界：只声明识别事实，不持有识别坐标、不读取图像、不比对舰名清单、不判断业务规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.application.controller.types import ShipType


# ── 槽位事实 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ShipInfo:
    """单个槽位的船只识别事实。

    Attributes:
        slot: 槽位号，按界面从左到右从 1 开始。
        name: 舰船名称；识别域不读取名称时为空。
        ship_type: 舰种；槽位为空位或识别失败时为空。
        level: 舰船等级；识别失败时为空。
    """

    slot: int
    name: str | None = None
    ship_type: ShipType | None = None
    level: int | None = None


@dataclass(frozen=True, slots=True)
class FleetRecognition:
    """出征准备页六个槽位的识别事实，舰名未与任何舰名清单比对。

    Attributes:
        name_texts: 六槽舰名的 OCR 原文，按槽位顺序；识别不到时为空。
        occupied: 六槽是否停有舰船，按槽位顺序。
        ship_types: 六槽舰种，按槽位顺序；识别失败时为空。
        ship_levels: 六槽等级，按槽位顺序；识别失败时为空。
    """

    name_texts: tuple[str | None, ...]
    occupied: tuple[bool, ...]
    ship_types: tuple[ShipType | None, ...]
    ship_levels: tuple[int | None, ...]


__all__ = ['FleetRecognition', 'ShipInfo']
