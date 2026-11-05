"""任务奖励收取执行器 — 后勤领域的轻量链路 (收取可领取的任务奖励)。

链路契约 (主页锚点):
    主页 → (主页有任务通知时) 任务页面 → 收取 (一键/单个 + 弹窗/确认) → 回主页。
    无通知时不动游戏, 直接在主页返回 — 天然安全。

调度关系:
    典型场景是定时轮询 (auto_daily 的 TimerTrigger, prio 1, 随远征周期),
    也可由 GUI 手动触发 (POST /api/reward/collect)。
    本链路自身短平快, 不设 _wait 断点。

旧代码参考: ``ops.reward.collect_rewards`` (兼容层见本文件尾部)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.mission import MissionPage
from autowsgr.application.navigation import goto_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.runtime.executor import BaseExecutor
from autowsgr.application.ui.controller.home.main_page import check_task_ready
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from autowsgr.application.runtime import RuntimeContext as GameContext


_log = get_logger('business.logistics.reward')


class RewardCheckExecutor(BaseExecutor):
    """任务奖励收取执行器: 有可领取奖励就收取, 没有就原路返回。"""

    def __init__(self, ctx: GameContext, params: dict | None = None, **kwargs: Any) -> None:
        super().__init__(ctx, params, **kwargs)

    def _execute(self) -> bool:
        """检查并收取任务奖励, 返回是否收取到了。"""
        goto_page(self.ctx, PageName.HOME)  # 锚点: 从主页出发

        screen = self.ctx.ctrl.screenshot()
        if not check_task_ready(screen):
            _log.debug('[Reward] 主页无任务通知, 跳过')
            self._report('checked', collected=0)
            return False

        goto_page(self.ctx, PageName.MISSION)
        page = MissionPage(self.ctx)
        collected = page.collect_rewards()

        goto_page(self.ctx, PageName.HOME)  # 锚点: 终态回主页
        _log.info('[Reward] 任务奖励收取完成, 收取={}', collected)
        self._report('checked', collected=1 if collected else 0)
        return collected


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容层 (auto_daily 定时器 / server HTTP / examples / 既有测试)
# ═══════════════════════════════════════════════════════════════════════════════


def collect_rewards(ctx: GameContext) -> bool:
    """兼容 API: 检查并收取任务奖励 (不参与暂停协作)。"""
    return RewardCheckExecutor(ctx).run()
