"""远征检查执行器 — 后勤领域的轻量链路 (收取已完成的远征)。

链路契约 (主页锚点):
    主页 → (主页有远征通知时) MAP → 远征面板收取 → 回主页。
    无通知时不动游戏, 直接在主页返回 — 天然安全。

调度关系:
    典型场景是「加急插入」: 处理器打断战斗任务后优先跑本链路
    (远征到期不收会闲置舰队), 跑完被打断的任务从头重跑。
    本链路自身短平快, 不设 _wait 断点。

旧代码参考: ``ops.expedition.collect_expedition``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sortie import (
    SortiePage,
    SortieTab,
)
from autowsgr.application.navigation import goto_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.runtime.executor import BaseExecutor
from autowsgr.application.ui.controller.home.main_page import check_expedition_ready
from autowsgr.application.ui.controller.operations.sortie_page.expedition_page import ExpeditionPage
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.runtime import RuntimeContext as GameContext


_log = get_logger('business.logistics.expedition')


class ExpeditionCheckExecutor(BaseExecutor):
    """远征检查执行器: 有完成远征就收取, 没有就原路返回。"""

    def __init__(self, ctx: GameContext, params: dict | None = None, **kwargs: Any) -> None:
        super().__init__(ctx, params, **kwargs)

    def _execute(self) -> bool:
        """检查并收取远征, 返回是否收取到了。"""
        goto_page(self.ctx, PageName.HOME)  # 锚点: 从主页出发

        screen = self.ctx.ctrl.screenshot()
        if not check_expedition_ready(screen):
            _log.debug('[Expedition] 主页无远征通知, 跳过')
            self._report('checked', collected=0)
            return False

        goto_page(self.ctx, PageName.SORTIE_MAP)
        sortie_page = SortiePage(self.ctx)
        screen = self.ctx.ctrl.screenshot()
        if not SortiePage.check_expedition_notification(screen):
            goto_page(self.ctx, PageName.HOME)  # 通知消失 (刚被收过), 原路返回
            self._report('checked', collected=0)
            return False

        sortie_page.select_tab(SortieTab.EXPEDITION)
        collected = ExpeditionPage(self.ctx).collect_expedition()

        goto_page(self.ctx, PageName.HOME)  # 锚点: 终态回主页
        _log.info('[Expedition] 远征检查完成, 收取 {} 个', collected)
        self._report('checked', collected=collected)
        return collected > 0


def collect_expedition(ctx: GameContext) -> bool:
    """调度器现成入口: 检查并收取远征 (等价于直接跑执行器, 不参与暂停协作)。"""
    return ExpeditionCheckExecutor(ctx).run()
