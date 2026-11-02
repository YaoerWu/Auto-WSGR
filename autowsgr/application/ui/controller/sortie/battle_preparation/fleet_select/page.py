"""模块功能：控制出征准备页的队伍选择与舰船槽位单击。

上层调用：
- application.ui.business：切换队伍、打开单个舰船槽位的船池页面。

下层依赖：
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不判断当前选中哪一队、不决定点哪个槽位、不重试。
队伍与槽位状态由 `controller.sortie.battle_preparation` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 顶部四个队伍页签的中心；高亮块随选中队伍变化，中心始终落在页签内。
FLEET_TAB_CLICKS = {
    1: (0.0883, 0.1695),
    2: (0.1969, 0.1695),
    3: (0.3274, 0.1695),
    4: (0.4477, 0.1695),
}

# 六个物理舰船槽位立绘区的中心；卡片宽 121px、间距 16-17px，点立绘区即可选中该槽位。
SHIP_SLOT_CLICKS = {
    1: (0.1149, 0.4625),
    2: (0.2290, 0.4625),
    3: (0.3438, 0.4625),
    4: (0.4586, 0.4625),
    5: (0.5727, 0.4625),
    6: (0.6875, 0.4625),
}


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class FleetSelectPanel:
    """出征准备页队伍选择区域的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def click_fleet_tab(self, fleet: int) -> None:
        """点击顶部队伍页签，把编队切换到指定队伍。

        Args:
            fleet: 队伍编号 1-4。

        Raises:
            ValueError: 队伍编号不在 1-4 范围内。
        """
        self._ctx.runtime.ctrl.click(*_resolve_click(fleet, FLEET_TAB_CLICKS, '队伍编号'))

    def click_ship_slot(self, slot: int) -> None:
        """点击舰船槽位的立绘区，打开该槽位的船池页面。

        Args:
            slot: 槽位编号 1-6，按画面从左到右。

        Raises:
            ValueError: 槽位编号不在 1-6 范围内。
        """
        self._ctx.runtime.ctrl.click(*_resolve_click(slot, SHIP_SLOT_CLICKS, '槽位编号'))


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _resolve_click(
    index: int,
    clicks: dict[int, tuple[float, float]],
    label: str,
) -> tuple[float, float]:
    """按编号取静态校准落点，编号越界时抛错，避免点到画面边缘。"""
    try:
        return clicks[index]
    except KeyError:
        valid = '、'.join(str(key) for key in clicks)
        raise ValueError(f'{label}必须是 {valid} 之一，实际为 {index}') from None


__all__ = [
    'FLEET_TAB_CLICKS',
    'SHIP_SLOT_CLICKS',
    'FleetSelectPanel',
]
