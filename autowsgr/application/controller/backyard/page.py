"""模块功能：在后院主页执行二级页跳转与各个方向的返回。

上层调用：
- application.navigation：执行后院与子页面之间的页面边动作。

下层依赖：
- application.controller.backyard.constants：提供后院点击落点。
- application.navigation.types：提供页面名称。

边界：只点击入口与返回按钮，不识别画面、不确认终态、不涉及二级页业务。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.controller.backyard import constants
from autowsgr.application.navigation.types import PageName
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.backyard')


# ── 后院导航目标 ────────────────────────────────────────────────────────────


class BackyardTarget(enum.Enum):
    """后院主页支持的四个二级页。"""

    CANTEEN = '餐厅'
    ACADEMY = '学院'
    RANK_ROOM = '军阶室'
    BATH = '浴室'

    @property
    def page_name(self) -> PageName:
        """返回导航器使用的页面名称。"""
        return _TARGET_PAGES[self]


_TARGET_PAGES: dict[BackyardTarget, PageName] = {
    BackyardTarget.CANTEEN: PageName.CANTEEN,
    BackyardTarget.ACADEMY: PageName.ACADEMY,
    BackyardTarget.RANK_ROOM: PageName.RANK_ROOM,
    BackyardTarget.BATH: PageName.BATH,
}


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class BackyardPage:
    """后院主页的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 导航 ────────────────────────────────────────────────────────────────

    def go_to(
        self,
        target: BackyardTarget,
        position: tuple[float, float] | None = None,
    ) -> None:
        """点击入口，进入对应的二级页。

        Args:
            target: 目标二级页。
            position: 导航器从入口模板读到的中心；为空时用静态坐标兜底。

        Raises:
            ValueError: 目标没有配置落点。
        """
        key = target.name.lower()
        fallback = constants.NAV_POSITIONS.get(key)
        if fallback is None:
            raise ValueError(f'后院没有该入口的落点: {target!r}')
        landing = position if position is not None else fallback
        _log.info(
            '[UI] 后院 → 进入二级页：target={!r}，position={!r}，source={!r}',
            target.value,
            landing,
            'center' if position is not None else 'fallback',
        )
        self._ctx.runtime.ctrl.click(*landing)

    # ── 返回 ────────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击退回按钮，回到上一级。

        后院主页按它回主页面，二级页按它回后院主页——两处是同一个按钮，
        因此二级页不需要各自实现，直接用本方法。
        """
        _log.info('[UI] 后院 → 退回上一级：position={!r}', constants.CLICK_BACK)
        self._ctx.runtime.ctrl.click(*constants.CLICK_BACK)

    def go_home(self) -> None:
        """点击二级页的通用回首页按钮，直接回主页面。

        这个按钮只在二级页上，四个二级页共用同一个落点，因此在这里实现一次。
        """
        _log.info('[UI] 后院 → 回首页：position={!r}', constants.CLICK_HOME)
        self._ctx.runtime.ctrl.click(*constants.CLICK_HOME)


__all__ = ['BackyardPage', 'BackyardTarget']
