"""模块功能：提供船只识别能力。

上层调用：
- business 与 dispatch：从 autowsgr.application.ui.ships 导入 ShipsService。

下层依赖：
- application.ui.ships.models：槽位事实。
- application.ui.ships.service：识别入口。
- application.ui.ships.types：舰种与识别域枚举。

边界：只导出稳定公开入口，不实现识别逻辑。
"""

from autowsgr.application.ui.ships.models import ShipInfo
from autowsgr.application.ui.ships.service import ShipsService
from autowsgr.application.ui.ships.types import ShipTaskType, ShipType


__all__ = ['ShipInfo', 'ShipTaskType', 'ShipType', 'ShipsService']
