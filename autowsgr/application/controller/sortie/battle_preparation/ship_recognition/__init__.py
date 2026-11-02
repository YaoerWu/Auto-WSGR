"""模块功能：提供船只识别能力。

上层调用：
- business 与 dispatch：从 autowsgr.application.controller.sortie.battle_preparation.ship_recognition 导入 ShipsService。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.models：槽位事实。
- application.controller.sortie.battle_preparation.ship_recognition.service：识别入口。
- application.controller.sortie.battle_preparation.ship_recognition.types：舰种与识别域枚举。

边界：只导出稳定公开入口，不实现识别逻辑。
"""

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
    ShipInfo,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.service import (
    ShipsService,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import (
    ShipTaskType,
    ShipType,
)


__all__ = ['ShipInfo', 'ShipTaskType', 'ShipType', 'ShipsService']
