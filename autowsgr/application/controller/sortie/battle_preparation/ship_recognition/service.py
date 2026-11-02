"""模块功能：提供船只识别的统一入口。

上层调用：
- business：按任务类型读取当前页面上的船只事实。
- dispatch：在任务执行过程中调用识别入口。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.models：提供各域共用的槽位事实。
- application.controller.sortie.battle_preparation.ship_recognition.models.exercise：读取演习对手浮窗。
- common.system.enums：提供统一的中文非法值错误。

边界：只按任务类型分派识别域，不导航、不点击、不判断阵容规则是否合格。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models.exercise import (
    recognize_rivals,
)
from autowsgr.common.system.enums import StrEnum


if TYPE_CHECKING:
    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.models import (
        ShipInfo,
    )
    from autowsgr.dispatch.context import ContextHandle


# ── 识别域 ──────────────────────────────────────────────────────────────────


class ShipTaskType(StrEnum):
    """船只识别按任务类型划分的识别域。"""

    EXERCISE = 'exercise'


class ShipsService:
    """船只识别入口，按任务类型路由到对应识别域。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def recognize_ships_info(self, task_type: ShipTaskType) -> tuple[ShipInfo, ...]:
        """按任务类型识别当前页面上的船只信息。

        Args:
            task_type: 船只识别域，决定读取哪一组槽位。

        Returns:
            按槽位号升序排列的识别事实；域不读取的字段为空。

        Raises:
            ValueError: 任务类型没有对应的船只识别域。
        """
        if task_type is ShipTaskType.EXERCISE:
            return recognize_rivals(self._ctx)
        raise ValueError(f'任务类型没有船只识别域: {task_type!r}')


__all__ = ['ShipsService']
