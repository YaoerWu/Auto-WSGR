"""模块功能：控制普通出征页面的单次点击。

上层调用：
- application.controller.sortie.battle：编排章节与地图选择时执行单次点击。
- application.navigation：执行出征页标签切换与返回的页面边动作。

下层依赖：
- battle_page.constants：提供章节槽位、地图翻页和出征入口的点击坐标。
- main_page：提供出征页页面壳的标签与返回动作。

边界：只做单次点击，不识别画面、不等待页面、不计算落点、不编排流程、不重试。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.page import SortiePage
from autowsgr.application.ui.controller.operations.sortie_page.battle_page import constants


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class BattlePage(SortiePage):
    """普通出征页面的单击控制器。"""

    # ── 章节与地图 ────────────────────────────────────────────────────────

    def click_chapter_slot(self, index: int) -> None:
        """点击一个固定章节槽位。

        Args:
            index: 当前画面中固定章节槽位的索引。

        Raises:
            ValueError: 槽位索引超出当前页面的固定范围。
        """
        if not 0 <= index < len(constants.CHAPTER_SLOT_POSITIONS):
            raise ValueError(
                f'章节槽位索引必须为 0-{len(constants.CHAPTER_SLOT_POSITIONS) - 1}, 收到: {index}',
            )
        self._ctx.runtime.ctrl.click(*constants.CHAPTER_SLOT_POSITIONS[index])

    def click_map_next(self) -> None:
        """点击章节右切按钮，查看后续章节。"""
        self._ctx.runtime.ctrl.click(*constants.CLICK_MAP_NEXT)

    def click_map_prev(self) -> None:
        """点击章节左切按钮，查看前置章节。"""
        self._ctx.runtime.ctrl.click(*constants.CLICK_MAP_PREV)

    # ── 出征入口 ──────────────────────────────────────────────────────────

    def click_enter_sortie(self) -> None:
        """点击普通出征入口，提交进入出征准备页。"""
        self._ctx.runtime.ctrl.click(*constants.CLICK_ENTER_SORTIE)


__all__ = ['BattlePage']
