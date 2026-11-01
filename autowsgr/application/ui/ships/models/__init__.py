"""模块功能：定义船只识别各域共用的事实模型。

上层调用：
- application.ui.ships.service：把各域识别结果作为统一出口返回。
- application.ui.ships.models 下的各识别域：产出并填充槽位事实。

下层依赖：
- application.ui.ships.types：提供舰种枚举。

边界：只声明识别事实，不持有识别坐标、不读取图像、不判断业务规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.application.ui.ships.types import ShipType


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


__all__ = ['ShipInfo']
