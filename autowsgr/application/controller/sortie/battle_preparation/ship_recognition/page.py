"""模块功能：操作出征准备页的六个舰队槽位。

上层调用：
- application.fleet_select：点开指定槽位进入船池换船。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition.constants：槽位落点与拖拽时长。
- dispatch.context：提供设备点击能力。

边界：只负责点击，不等待页面切换、不识别页面、不判断该槽位是否为空。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import constants


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


class FleetSlotPage:
    """出征准备页六个舰队槽位的点击入口。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def click_slot(self, slot: int) -> None:
        """点开指定槽位，进入船池选船。

        Args:
            slot: 槽位序号，按画面从左到右从 1 开始。

        Raises:
            ValueError: 槽位序号不在 1 到 6 之间。
        """
        if not 1 <= slot <= constants.FLEET_SLOT_COUNT:
            raise ValueError(
                f'槽位序号必须在 1 到 {constants.FLEET_SLOT_COUNT} 之间，实际为 {slot}'
            )
        self._ctx.runtime.ctrl.click(*constants.CLICK_SHIP_SLOTS[slot - 1])

    def drag_slot(self, source: int, target: int) -> None:
        """把一艘舰船从源槽位拖到目标槽位。

        Args:
            source: 源槽位序号，从 1 开始。
            target: 目标槽位序号，从 1 开始。

        Raises:
            ValueError: 槽位序号不在 1 到 6 之间。
        """
        for slot in (source, target):
            if not 1 <= slot <= constants.FLEET_SLOT_COUNT:
                raise ValueError(
                    f'槽位序号必须在 1 到 {constants.FLEET_SLOT_COUNT} 之间，实际为 {slot}'
                )
        self._ctx.runtime.ctrl.swipe(
            *constants.CLICK_SHIP_SLOTS[source - 1],
            *constants.CLICK_SHIP_SLOTS[target - 1],
            constants.DRAG_DURATION_SECONDS,
        )


__all__ = ['FleetSlotPage']
