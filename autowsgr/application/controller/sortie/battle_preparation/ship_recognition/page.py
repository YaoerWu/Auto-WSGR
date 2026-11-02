"""模块功能：操作出征准备页的六个舰队槽位。

上层调用：
- application.fleet_select：点开指定槽位进入船池换船。

下层依赖：
- dispatch.context：提供设备点击能力。

边界：只负责点击，不等待页面切换、不识别页面、不判断该槽位是否为空。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 点击落点 ────────────────────────────────────────────────────────────────

# 六个槽位卡片中心的归一化坐标，校准基准 1280x720。x 取卡片横向中心
# （槽左边界 63 / 212 / 361 / 510 / 659 / 808 加半个卡宽 67.5），
# y 取卡片上半部 0.4625，避开底部的血条与舰名。
CLICK_SHIP_SLOTS = (
    (0.10195313, 0.46250000),
    (0.21835937, 0.46250000),
    (0.33476563, 0.46250000),
    (0.45117188, 0.46250000),
    (0.56757813, 0.46250000),
    (0.68398437, 0.46250000),
)

# 拖拽一艘舰船到另一个槽位的滑动时长，太短会被游戏当成点按。
DRAG_DURATION_SECONDS = 0.5


# ── 页面操作 ────────────────────────────────────────────────────────────────


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
        if not 1 <= slot <= len(CLICK_SHIP_SLOTS):
            raise ValueError(f'槽位序号必须在 1 到 {len(CLICK_SHIP_SLOTS)} 之间，实际为 {slot}')
        self._ctx.runtime.ctrl.click(*CLICK_SHIP_SLOTS[slot - 1])

    def drag_slot(self, source: int, target: int) -> None:
        """把一艘舰船从源槽位拖到目标槽位。

        Args:
            source: 源槽位序号，从 1 开始。
            target: 目标槽位序号，从 1 开始。

        Raises:
            ValueError: 槽位序号不在 1 到 6 之间。
        """
        for slot in (source, target):
            if not 1 <= slot <= len(CLICK_SHIP_SLOTS):
                raise ValueError(
                    f'槽位序号必须在 1 到 {len(CLICK_SHIP_SLOTS)} 之间，实际为 {slot}',
                )
        self._ctx.runtime.ctrl.swipe(
            *CLICK_SHIP_SLOTS[source - 1],
            *CLICK_SHIP_SLOTS[target - 1],
            DRAG_DURATION_SECONDS,
        )


__all__ = ['CLICK_SHIP_SLOTS', 'DRAG_DURATION_SECONDS', 'FleetSlotPage']
