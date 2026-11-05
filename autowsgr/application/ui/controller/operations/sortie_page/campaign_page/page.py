"""模块功能：编排战役页面的难度选择和出征准备入口。

上层调用：
- business.combat.campaign：选择战役并进入出征准备页面。

下层依赖：
- application.ui.controller.operations.sortie_page.main_page：提供 sortie_page 页面壳和顶部标签。
- application.ui.controller.operations.sortie_page.campaign_page.constants：提供页面动作坐标。
- application.ui.controller.operations.sortie_page.campaign_page.recognition：提供难度事实识别。
- common.device.interaction：确认目标页面到达和导航失败。

边界：
只编排战役出征入口，不实现 OCR、像素识别、跨页面调度或运行时状态管理。
"""

from __future__ import annotations

import time

from autowsgr.application.controller.sortie import (
    SortiePage,
    SortieTab,
)
from autowsgr.application.navigation.interaction import NavigationError, wait_for_page
from autowsgr.application.navigation.types import PageName
from autowsgr.application.ui.controller.operations.sortie_page.campaign_page import (
    constants,
    recognition,
)
from autowsgr.common.system.logger import get_logger


_log = get_logger('ui.campaign_page')


# ── 页面流程参数 ────────────────────────────────────────────────────────────────────

_CAMPAIGN_TAB_SETTLE_SECONDS: float = 0.5
"""切换 sortie 顶部标签后等待页面稳定的时间。"""

_DIFFICULTY_POLL_SECONDS: float = 0.25
"""难度切换后轮询页面状态的间隔。"""

_DIFFICULTY_MAX_ATTEMPTS: int = 10
"""难度切换后确认目标状态的最大次数。"""

_DIFFICULTY_SETTLE_SECONDS: float = 0.75
"""难度状态确认后等待战役入口稳定的时间。"""

_CAMPAIGN_ENTRY_SETTLE_SECONDS: float = 0.5
"""点击战役入口后等待出征准备页加载的时间。"""


class CampaignPage(SortiePage):
    """战役页面控制器。"""

    # ── 战役出征流程 ────────────────────────────────────────────────────────────────

    def enter_campaign(
        self,
        map_index: int = 2,
        difficulty: str = 'hard',
        campaign_name: str = '未知',
    ) -> None:
        """选择战役难度和类型，并进入出征准备页面。

        Args:
            map_index: 战役编号，范围为 1-5。
            difficulty: 目标难度，只能是 ``"easy"`` 或 ``"hard"``。
            campaign_name: 用于日志的战役名称。

        Raises:
            ValueError: 战役编号或难度无效。
            NavigationError: 超时未到达出征准备页面。
            RuntimeError: 难度切换后仍无法确认目标状态。
        """
        if map_index not in constants.CAMPAIGN_POSITIONS:
            raise ValueError(f'战役编号必须为 1-5，收到: {map_index}')
        if difficulty not in ('easy', 'hard'):
            raise ValueError(f'难度必须为 easy 或 hard，收到: {difficulty}')

        # 战役流程会反向依赖出征准备页，局部导入用于避免页面包初始化循环。
        from autowsgr.application.ui.controller.fleet import BattlePreparationPage

        _log.info(
            '[UI] 战役页面 → 进入：战役={!r}，难度={!r}，状态=开始',
            campaign_name,
            difficulty,
        )

        # 1. 切换到战役面板并等待入口稳定。
        self.select_tab(SortieTab.CAMPAIGN)
        time.sleep(_CAMPAIGN_TAB_SETTLE_SECONDS)

        # 2. 读取当前难度，必要时切换并确认目标状态。
        current = recognition.recognize_difficulty(self._ctrl.screenshot())
        if current != difficulty:
            _log.info(
                '[UI] 战役页面 → 切换难度：当前难度={!r}，目标难度={!r}，状态=开始',
                current,
                difficulty,
            )
            self._ctrl.click(*constants.CLICK_DIFFICULTY)
            for attempt in range(1, _DIFFICULTY_MAX_ATTEMPTS + 1):
                time.sleep(_DIFFICULTY_POLL_SECONDS)
                current = recognition.recognize_difficulty(self._ctrl.screenshot())
                if current == difficulty:
                    _log.info(
                        '[UI] 战役页面 → 切换难度：结果=成功，尝试次数={}',
                        attempt,
                    )
                    break
            else:
                _log.error(
                    '[UI] 战役页面 → 切换难度：目标难度={!r}，结果=失败，原因=未确认',
                    difficulty,
                )
                raise RuntimeError('无法确认战役难度')
            time.sleep(_DIFFICULTY_SETTLE_SECONDS)

        # 3. 选择战役并确认进入出征准备页面。
        self._ctrl.click(*constants.CAMPAIGN_POSITIONS[map_index])
        time.sleep(_CAMPAIGN_ENTRY_SETTLE_SECONDS)
        try:
            wait_for_page(
                self._ctrl,
                checker=BattlePreparationPage.check_current_page,
                source=f'战役页面-{campaign_name}',
                target=PageName.BATTLE_PREPARATION.value,
            )
        except NavigationError:
            _log.error(
                '[UI] 战役页面 → 进入：战役={!r}，结果=失败',
                campaign_name,
            )
            raise
        _log.info(
            '[UI] 战役页面 → 进入：战役={!r}，结果=成功',
            campaign_name,
        )
