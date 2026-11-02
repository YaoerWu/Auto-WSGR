"""模块功能：提供出征准备页的舰队识别与槽位操作入口。

上层调用：
- application.fleet_select：读取六槽舰名原文、舰种、等级与血条状态，并点开槽位进船池。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.checker：识别入口与血条状态模型。
- application.controller.sortie.battle_preparation.ship_recognition.models：识别事实模型。
- application.controller.sortie.battle_preparation.ship_recognition.page：槽位点击入口。
- application.controller.types：舰种枚举。

边界：只导出稳定公开入口，不实现识别逻辑，不比对舰名清单。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.checker import (
    ShipDamage,
    read_fleet_recognition,
    read_ship_damage,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    FleetRecognition,
    ShipInfo,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    FleetSlotPage,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.service import (
    ShipsService,
    ShipTaskType,
)
from autowsgr.application.controller.types import ShipType


__all__ = [
    'FleetRecognition',
    'FleetSlotPage',
    'ShipDamage',
    'ShipInfo',
    'ShipTaskType',
    'ShipType',
    'ShipsService',
    'read_fleet_recognition',
    'read_ship_damage',
]
