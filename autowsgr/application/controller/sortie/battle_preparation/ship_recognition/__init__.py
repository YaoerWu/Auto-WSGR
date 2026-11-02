"""模块功能：提供船只识别能力。

上层调用：
- business 与 dispatch：从 autowsgr.application.controller.sortie.battle_preparation.ship_recognition 导入 ShipsService。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.models：槽位事实。
- application.controller.sortie.battle_preparation.ship_recognition.service：识别入口。
- application.controller.types：舰种枚举。
- application.controller.sortie.battle_preparation.ship_recognition.service：识别域与识别入口。

边界：只导出稳定公开入口，不实现识别逻辑。
"""

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    ShipInfo,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.service import (
    ShipsService,
    ShipTaskType,
)
from autowsgr.application.controller.types import ShipType


__all__ = ['ShipInfo', 'ShipTaskType', 'ShipType', 'ShipsService']
