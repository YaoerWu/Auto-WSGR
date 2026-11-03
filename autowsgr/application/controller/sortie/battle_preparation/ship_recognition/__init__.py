"""模块功能：提供出征准备页的舰队识别与槽位操作入口。

上层调用：
- application.fleet_select：读取六槽血条状态与舰种、等级、舰名原文，并点开槽位进船池。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.checker：四个槽位识别入口。
- application.controller.sortie.battle_preparation.ship_recognition.constants：槽位状态枚举。
- application.controller.sortie.battle_preparation.ship_recognition.page：槽位点击入口。

边界：只导出稳定公开入口，不实现识别逻辑，不解析识别原文，不比对舰名清单。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.checker import (
    read_ship_damage,
    read_ship_levels,
    read_ship_names,
    read_ship_types,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.constants import (
    ShipDamage,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    FleetSlotPage,
)


__all__ = [
    'FleetSlotPage',
    'ShipDamage',
    'read_ship_damage',
    'read_ship_levels',
    'read_ship_names',
    'read_ship_types',
]
