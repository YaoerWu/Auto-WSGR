"""模块功能：控制出征准备页快速整备区域的单次点击。

上层调用：
- 暂无生产调用方：整备流程接线（任务书 P4）后由应用层按业务需要切换补给开关或整备页签。

下层依赖：
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不判断当前状态、不决定是否整备、不重试。
状态与落点读取由 `controller.sortie.battle_preparation.quick_maintenance` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 左下角自动补给勾选框的中心；框体像素范围 [38, 645, 92, 701]。
CLICK_AUTO_SUPPLY = (0.0508, 0.9347)

# 底部功能栏快速修理页签的中心；页签像素范围 [470, 539, 649, 588]。
CLICK_QUICK_REPAIR = (0.4371, 0.7826)

# 右侧修理面板「全部修理」按钮的中心；按钮像素范围 [1022, 464, 1173, 517]。
CLICK_ALL_REPAIR = (0.8578, 0.6819)


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class QuickMaintenancePanel:
    """出征准备页快速整备区域的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def click_auto_supply(self, center: tuple[float, float] | None = None) -> None:
        """点击自动补给勾选框，切换它的开启状态。

        Args:
            center: 识别得到的勾选框中心；省略时回退到静态校准坐标。
        """
        self._ctx.runtime.ctrl.click(*_resolve_center(center, CLICK_AUTO_SUPPLY))

    def click_quick_repair(self, center: tuple[float, float] | None = None) -> None:
        """点击快速修理页签，把底部面板切到修理视图。

        Args:
            center: 识别得到的页签中心；省略时回退到静态校准坐标。
        """
        self._ctx.runtime.ctrl.click(*_resolve_center(center, CLICK_QUICK_REPAIR))

    def click_all_repair(self, center: tuple[float, float] | None = None) -> None:
        """点击「全部修理」按钮，一次修好所有受损舰船。

        Args:
            center: 识别得到的按钮中心；省略时回退到静态校准坐标。
        """
        self._ctx.runtime.ctrl.click(*_resolve_center(center, CLICK_ALL_REPAIR))


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _resolve_center(
    center: tuple[float, float] | None,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    """优先使用识别得到的落点，识别不到时回退到静态校准坐标。"""
    return fallback if center is None else center


__all__ = [
    'CLICK_ALL_REPAIR',
    'CLICK_AUTO_SUPPLY',
    'CLICK_QUICK_REPAIR',
    'QuickMaintenancePanel',
]
