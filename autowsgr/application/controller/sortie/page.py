"""模块功能：控制出征页页面壳的单次点击。

上层调用：
- application.ui.navigation：进入某个顶部标签，或离开出征页。

下层依赖：
- main_page.constants：提供标签落点与返回落点。
- common.device.service：通过 `ctx.runtime.ctrl` 执行点击。

边界：只做**单次点击**，不识别画面、不等待页面、不编排流程、不重试。
顶部标签的识别由 `sortie` 负责，切换确认由导航器负责；标签落点优先使用调用方
传入的识别中心，缺省时用固定落点兜底。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.operations.sortie_page.main_page import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.sortie_page.main_page')


# ── 顶部业务标签 ────────────────────────────────────────────────────────────


class SortieTab(enum.Enum):
    """出征页顶部的五个业务标签。"""

    SORTIE = '出征'
    EXERCISE = '演习'
    EXPEDITION = '远征'
    CAMPAIGN = '战役'
    DECISIVE = '决战'


SORTIE_TAB_LIST: tuple[SortieTab, ...] = tuple(SortieTab)
"""顶部标签的显示顺序。"""


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class SortiePage:
    """出征页页面壳的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 导航 ────────────────────────────────────────────────────────────────

    def go_to(self, tab: SortieTab, position: tuple[float, float] | None = None) -> None:
        """点击目标顶部标签。

        Args:
            tab: 要打开的出征业务标签。
            position: 识别产出的标签中心；为空时使用固定落点。
        """
        target = position or constants.TAB_POSITIONS[tab.name.lower()]
        _log.info('[UI] 出征页 → 切换标签：tab={!r}，position={!r}', tab.value, target)
        self._ctx.runtime.ctrl.click(*target)

    def go_back(self) -> None:
        """点击返回按钮，离开出征页。"""
        _log.info('[UI] 出征页 → 返回：position={!r}', constants.CLICK_BACK)
        self._ctx.runtime.ctrl.click(*constants.CLICK_BACK)
