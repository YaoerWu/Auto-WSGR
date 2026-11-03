"""模块功能：控制船池页面的单次操作。

上层调用：
- application.fleet_select.operation.ship_select：换船流程里点击搜索框、输入舰名、点卡、滑动列表。

下层依赖：
- application.controller.sortie.battle_preparation.page：共用标题栏的返回落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击、滑动与文字输入。

边界：只做**单次操作**，不识别画面、不等待页面、不判断结果、不重试、不编排流程。
页面识别由 `controller.sortie.battle_preparation.ship_pool.checker` 负责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.page import CLICK_BACK


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 校准 ────────────────────────────────────────────────────────────────────

# 搜索输入框的中心。
CLICK_SEARCH_BOX = (0.7292, 0.0556)

# 软键盘右上角的收起按钮。
CLICK_DISMISS_KEYBOARD = (0.5208, 0.0926)

# 提交搜索框内容用的回车键（KEYCODE_ENTER）。
KEYCODE_ENTER = 66

# 卡片详情页的「移除舰船」按钮。
CLICK_REMOVE_SHIP = (0.0865, 0.3093)

# 列表的纵向滑动区间：从下往上拖一屏，用于看后面的卡片。
SCROLL_START = (0.4, 0.55)
SCROLL_END = (0.4, 0.30)
SCROLL_DURATION_SECONDS = 0.4


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class ShipPoolPage:
    """船池页面的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    def click_search_box(self) -> None:
        """点击搜索框，唤起软键盘。"""
        self._ctx.runtime.ctrl.click(*CLICK_SEARCH_BOX)

    def input_ship_name(self, name: str) -> None:
        """向已唤起的搜索框输入舰名。

        Args:
            name: 输入到搜索框的文本。
        """
        self._ctx.runtime.ctrl.text(name)

    def confirm_search(self) -> None:
        """按回车提交搜索框里的舰名，让列表按名字过滤。"""
        self._ctx.runtime.ctrl.key_event(KEYCODE_ENTER)

    def dismiss_keyboard(self) -> None:
        """点击收起按钮，关闭软键盘。"""
        self._ctx.runtime.ctrl.click(*CLICK_DISMISS_KEYBOARD)

    def click_card_at(self, center: tuple[float, float]) -> None:
        """点击船池列表上某张卡片。

        Args:
            center: 卡片上某段文字的归一化中心，通常来自列表识别结果。
        """
        self._ctx.runtime.ctrl.click(*center)

    def click_remove_ship(self) -> None:
        """点击卡片详情页的「移除舰船」按钮。"""
        self._ctx.runtime.ctrl.click(*CLICK_REMOVE_SHIP)

    def scroll_list_down(self) -> None:
        """把船池列表向下滚动一屏，露出后面的卡片。"""
        self._ctx.runtime.ctrl.swipe(*SCROLL_START, *SCROLL_END, SCROLL_DURATION_SECONDS)

    def go_back(self) -> None:
        """点击返回按钮，退到上一级页面。"""
        self._ctx.runtime.ctrl.click(*CLICK_BACK)


__all__ = [
    'CLICK_DISMISS_KEYBOARD',
    'CLICK_REMOVE_SHIP',
    'CLICK_SEARCH_BOX',
    'KEYCODE_ENTER',
    'SCROLL_DURATION_SECONDS',
    'SCROLL_END',
    'SCROLL_START',
    'ShipPoolPage',
]
