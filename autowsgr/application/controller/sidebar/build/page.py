"""模块功能：在建造页执行标签切换与返回。

上层调用：
- application.navigation：执行建造页的标签切换与返回主页的页面边动作。

下层依赖：
- application.ui.controller.sidebar.build_page.constants：提供标签与返回落点。

边界：只点击标签与返回按钮，不识别画面、不确认终态、不编排建造业务。
建造与解装的业务流程尚未迁移到新链路，等第二阶段移植后再补回本模块。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.sidebar.build_page import constants
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import (
        ShipType,
    )
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.sidebar.build_page')


# ── 页面标签 ─────────────────────────────────────────────────────────────────


class BuildTab(enum.Enum):
    """建造页面标签组。"""

    BUILD = '建造'
    DESTROY = '解体'
    DEVELOP = '开发'
    DISCARD = '废弃'


# ── 页面控制器 ──────────────────────────────────────────────────────────────


class BuildPage:
    """建造页面的单击控制器。"""

    def __init__(self, ctx: ContextHandle) -> None:
        """绑定任务上下文。

        Args:
            ctx: 提供设备服务的 dispatch 上下文句柄。
        """
        self._ctx = ctx

    # ── 建造与解体业务 ────────────────────────────────────────────────────────

    # 建造与解体的流程编排在 workflow.py；本方法是对外入口，只负责切换标签再交给流程。
    # workflow 依赖的旧模块尚未迁移，因此局部导入，避免拖累导航器导入本模块。

    def build(
        self,
        *,
        build_count: int = 1,
        collect_completed: bool = True,
        build_type: str = 'ship',
        allow_fast_build: bool = False,
    ) -> int:
        """切换到对应标签并执行收取、建造流程。

        Args:
            build_count: 要新建的数量，必须为非负整数。
            collect_completed: 是否先收取已完成的建造项目。
            build_type: 建造类型，`ship` 表示舰船，其他值表示装备。
            allow_fast_build: 是否先处理可快速建造的槽位。

        Returns:
            实际收取的数量。

        Raises:
            TypeError: build_count 不是整数。
            ValueError: build_count 小于零。
            RuntimeError: 建造队列已满、仓库已满或资源页面未出现。
        """
        from autowsgr.application.ui.controller.sidebar.build_page import workflow

        if not isinstance(build_count, int) or isinstance(build_count, bool):
            _log.error(
                '[UI] 建造页 → 拒绝建造：建造数量={!r}，期望类型=非负整数，结果=拒绝',
                build_count,
            )
            raise TypeError(f'建造数量必须为整数，收到: {build_count!r}')
        if build_count < 0:
            _log.error(
                '[UI] 建造页 → 拒绝建造：建造数量={!r}，期望范围=>=0，结果=拒绝',
                build_count,
            )
            raise ValueError(f'建造数量不能为负数，收到: {build_count}')

        target_tab = BuildTab.BUILD if build_type == 'ship' else BuildTab.DEVELOP
        self.go_to_tab(target_tab)
        return workflow.build(
            self._ctx.runtime.ctrl,
            build_count=build_count,
            collect_completed=collect_completed,
            build_type=build_type,
            allow_fast_build=allow_fast_build,
        )

    def destroy_ships(
        self,
        ship_types: list[ShipType] | None = None,
        *,
        remove_equipment: bool = True,
    ) -> None:
        """切换到解体标签并执行完整解装流程。

        Args:
            ship_types: 要解体的舰种列表；`None` 表示不过滤舰种。
            remove_equipment: 是否在解装前卸下装备。
        """
        from autowsgr.application.ui.controller.sidebar.build_page import workflow

        self.go_to_tab(BuildTab.DESTROY)
        workflow.destroy_ships(
            self._ctx.runtime.ctrl,
            ship_types=ship_types,
            remove_equipment=remove_equipment,
        )

    # ── 标签切换 ──────────────────────────────────────────────────────────────

    def go_to_tab(self, tab: BuildTab) -> None:
        """点击顶部标签，切到对应内容。

        只负责点击；是否真的切过去了由导航器用标签的 checker 确认。

        Args:
            tab: 目标标签。

        Raises:
            ValueError: 标签没有配置落点。
        """
        position = constants.TAB_POSITIONS.get(tab.name.lower())
        if position is None:
            raise ValueError(f'建造页没有该标签的落点: {tab!r}')
        _log.info('[UI] 建造页面 → 切换标签：tab={!r}，position={!r}', tab.value, position)
        self._ctx.runtime.ctrl.click(*position)

    # ── 页面返回 ──────────────────────────────────────────────────────────────

    def go_back(self) -> None:
        """点击左上角返回按钮，离开建造页。"""
        _log.info('[UI] 建造页 → 返回：position={!r}', constants.CLICK_BACK)
        self._ctx.runtime.ctrl.click(*constants.CLICK_BACK)


__all__ = ['BuildPage', 'BuildTab']
