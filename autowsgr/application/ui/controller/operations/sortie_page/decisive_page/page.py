"""模块功能：执行决战总览页的页面检查、章节操作、磁盘购买和页面回退。

上层调用：
- application.ui.controller.operations.sortie_page.main_page：选择决战顶部标签。
- application.navigation：确认决战总览页并执行跨页面回退。
- business.combat.decisive：读取章节状态并推进决战入口流程。
- testing.ui：验证决战总览页识别和操作。

下层依赖：
- application.ui.controller.operations.sortie_page.decisive_page.constants：提供总览页校准。
- application.ui.controller.operations.sortie_page.decisive_page.recognition：读取章节编号 OCR。
- common.device.interaction、common.vision：执行页面等待、模板匹配和像素检查。

本模块只执行总览页 UI 操作；章节决策、OCR 算法和跨任务调度由对应模块负责。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie import (
    SortiePage,
    SortieTab,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CLICK_BACK,
    CLICK_BUY_CONFIRM,
    CLICK_BUY_RESOURCE,
    CLICK_BUY_TICKET_OPEN,
    CLICK_ENTER_DECISIVE,
    CLICK_ENTER_MAP,
    CLICK_NEXT_CHAPTER,
    CLICK_PREV_CHAPTER,
    ENTRY_STATUS_ROI,
    RESET_BUTTON_ROI,
    RESET_ENTRY_ROI,
    STAGE_CHECK_COLOR,
    STAGE_CHECK_POINTS,
    STAGE_CHECK_TOLERANCE,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.recognition import (
    read_chapter_number,
)
from autowsgr.application.navigation.interaction import (
    click_and_wait_for_page,
    confirm_operation,
)
from autowsgr.application.navigation.types import PageName
from autowsgr.application.vision.resources import Templates
from autowsgr.business.combat.decisive.types import DecisiveEntryStatus
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker, PageMatch, PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.application.ui.controller.context import UIContext as GameContext
    from autowsgr.common.vision import OCREngine


_log = get_logger('ui.decisive')

# 页面流程参数。
_CHAPTER_SWITCH_DELAY = 0.8  # 章节按钮点击后的页面动画等待时间。
_CHAPTER_NAV_MAX_ATTEMPTS = 8  # 章节导航读取失败时的最大重试次数。
MIN_CHAPTER = 1  # 决战章节编号允许的最小值。
MAX_CHAPTER = 6  # 决战章节编号允许的最大值。


class DecisiveEntryPage(SortiePage):
    """决战入口页面控制器，负责从 sortie_page 进入决战总览。"""

    def enter_decisive(self) -> None:
        """选择决战顶部标签并进入决战总览页。

        Raises:
            NavigationError: 点击入口后未到达决战总览页。
        """
        _log.info('[UI] sortie_page → 决战总览')
        time.sleep(0.5)
        self.select_tab(SortieTab.DECISIVE)
        time.sleep(0.5)

        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_ENTER_DECISIVE,
            checker=DecisiveBattlePage.check_current_page,
            source='sortie_page-决战',
            target=PageName.DECISIVE_BATTLE,
        )


class DecisiveBattlePage:
    """决战总览页控制器。"""

    def __init__(
        self,
        ctx: GameContext,
        ocr: OCREngine | None = None,
    ) -> None:
        """保存调用方注入的上下文、设备控制器和 OCR 引擎。

        Args:
            ctx: 当前运行时 UI 上下文。
            ocr: 可选的 OCR 引擎；未传入时使用上下文中的引擎。
        """
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._ocr = ocr or ctx.ocr

    # 页面检查。

    @staticmethod
    def check_current_page(screen: np.ndarray) -> PageMatch:
        """检查截图是否为决战总览页。"""
        result = ImageChecker.find_any(
            screen,
            Templates.Decisive.entry_status_templates(),
            roi=ENTRY_STATUS_ROI,
            confidence=0.8,
        )
        name = PageName.DECISIVE_BATTLE.value
        if result is None:
            return PageMatch(name=name, matched=False, score=0.0)
        return PageMatch(name=name, matched=True, score=result.confidence)

    # 总览页状态读取。

    @staticmethod
    def recognize_stage(screen: np.ndarray, chapter: int) -> int | None:  # noqa: PLR0911
        """识别当前小关 (1-3)，或在本章完成时返回 ``None``。"""
        check_points = STAGE_CHECK_POINTS.get(chapter)
        if check_points is None:
            _log.warning('[决战] 无法读取未知章节 {} 的小关进度', chapter)
            return 0

        node_exists = [
            PixelChecker.check_pixel(
                screen,
                x,
                y,
                STAGE_CHECK_COLOR,
                STAGE_CHECK_TOLERANCE,
            )
            for x, y in check_points
        ]
        if not node_exists[0]:
            _log.warning('[决战] 小节节点进度异常: 第 1 个节点不存在')
            return 0
        if not node_exists[1]:
            return 1
        if not node_exists[2]:
            return 2

        if ImageChecker.template_exists(
            screen,
            Templates.Decisive.ENTRY_REFRESH,
            roi=ENTRY_STATUS_ROI,
            confidence=0.8,
        ):
            _log.info('[决战] 入口为可重置状态，三个小节均已完成')
            return None

        entry_challenging = ImageChecker.template_exists(
            screen,
            Templates.Decisive.ENTRY_CHALLENGING,
            roi=ENTRY_STATUS_ROI,
            confidence=0.8,
        )
        reset_button = ImageChecker.template_exists(
            screen,
            Templates.Decisive.RESET_BUTTON,
            roi=RESET_BUTTON_ROI,
            confidence=0.8,
        )
        if entry_challenging and reset_button:
            return 3

        _log.warning('[决战] 三个小节节点均存在，但入口状态无法确认第三节或完成状态')
        return 0

    def read_stage(self, screen: np.ndarray, chapter: int) -> int | None:
        """读取指定章节当前正在进行的小关编号。

        Args:
            screen: RGB 截图。
            chapter: 决战章节编号。

        Returns:
            当前小关编号 (1-3)；全部小关通过时返回 ``None``，未知或无法确认时返回 ``0``。
        """
        return self.recognize_stage(screen, chapter)

    def read_chapter(self, screen: np.ndarray | None = None) -> int | None:
        """读取总览页当前章节编号，并委托 OCR 识别实现。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return read_chapter_number(self._ocr, screen)

    def read_entry_status(
        self,
        *,
        timeout: float = 10.0,
        interval: float = 0.3,
        confidence: float = 0.8,
    ) -> DecisiveEntryStatus:
        """读取决战总览页的入口状态。

        Args:
            timeout: 最长等待时间，单位为秒。
            interval: 截图检查间隔，单位为秒。
            confidence: 入口状态模板的匹配置信度阈值。

        Returns:
            匹配到的决战入口状态。

        Raises:
            TimeoutError: 超时仍未匹配到入口状态。
        """
        templates = Templates.Decisive.entry_status_templates()
        statuses = list(DecisiveEntryStatus)
        deadline = time.monotonic() + timeout

        while True:
            detail = ImageChecker.find_any(
                self._ctrl.screenshot(),
                templates,
                roi=ENTRY_STATUS_ROI,
                confidence=confidence,
            )
            if detail is not None:
                index = next(
                    index
                    for index, template in enumerate(templates)
                    if template.name == detail.template_name
                )
                status = statuses[index]
                _log.info('[决战] 入口状态: {}', status.value)
                return status

            if time.monotonic() >= deadline:
                raise TimeoutError(f'决战入口状态检测超时 ({timeout}s)')
            time.sleep(interval)

    # 总览页原子动作。

    def click_enter_map(self) -> None:
        """点击进入当前章节的决战地图。"""
        _log.info('[决战] 总览页 -> 进入地图')
        self._ctrl.click(*CLICK_ENTER_MAP)

    # 章节导航。

    def click_previous_chapter(self) -> None:
        """点击前一章节按钮。"""
        _log.info('[决战] 切换到前一章节')
        self._ctrl.click(*CLICK_PREV_CHAPTER)
        time.sleep(_CHAPTER_SWITCH_DELAY)

    def click_next_chapter(self) -> None:
        """点击后一章节按钮。"""
        _log.info('[决战] 切换到后一章节')
        self._ctrl.click(*CLICK_NEXT_CHAPTER)
        time.sleep(_CHAPTER_SWITCH_DELAY)

    # 总览页资源操作。

    def buy_ticket(self, use: str = 'steel', times: int = 3) -> None:
        """使用指定资源购买决战磁盘。

        Args:
            use: 资源类型，支持 ``oil``、``ammo``、``steel`` 和 ``aluminum``。
            times: 点击资源按钮的次数。

        Raises:
            ValueError: 资源类型不受支持。
        """
        if use not in CLICK_BUY_RESOURCE:
            raise ValueError(f'资源类型必须为 oil/ammo/steel/aluminum，收到 {use}')

        _log.info('[决战] 购买磁盘：资源={}, 次数={}', use, times)
        self._ctrl.click(*CLICK_BUY_TICKET_OPEN)
        time.sleep(1.5)

        for _ in range(times):
            self._ctrl.click(*CLICK_BUY_RESOURCE[use])
            time.sleep(1.0)

        self._ctrl.click(*CLICK_BUY_CONFIRM)
        time.sleep(1.0)

    def reset_chapter(self) -> bool:
        """点击重置关卡并确认清空当前章节进度。

        Returns:
            船坞未满且确认操作完成时返回 ``True``；检测到船坞已满时返回 ``False``。
        """
        from autowsgr.application.navigation.interaction import NavigationError

        _log.info('[决战] 重置当前章节')
        deadline = time.monotonic() + 5.0
        match = None
        match_source: str | None = None
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            match = ImageChecker.find_template(
                screen,
                Templates.Decisive.RESET_BUTTON,
                roi=RESET_BUTTON_ROI,
                confidence=0.8,
            )
            match_source = 'reset_button' if match is not None else None
            if match is None:
                match = ImageChecker.find_template(
                    screen,
                    Templates.Decisive.ENTRY_REFRESH,
                    roi=RESET_ENTRY_ROI,
                    confidence=0.8,
                )
                match_source = 'entry_refresh' if match is not None else None
            if match is not None:
                break
            time.sleep(0.2)

        if match is None:
            raise TimeoutError('未识别到「重置关卡」按钮，拒绝点击')

        for attempt in range(2):
            if attempt:
                screen = self._ctrl.screenshot()
                match = ImageChecker.find_template(
                    screen,
                    Templates.Decisive.RESET_BUTTON,
                    roi=RESET_BUTTON_ROI,
                    confidence=0.8,
                )
                match_source = 'reset_button' if match is not None else None
                if match is None:
                    match = ImageChecker.find_template(
                        screen,
                        Templates.Decisive.ENTRY_REFRESH,
                        roi=RESET_ENTRY_ROI,
                        confidence=0.8,
                    )
                    match_source = 'entry_refresh' if match is not None else None
                if match is None:
                    raise TimeoutError('重试时未识别到「重置关卡」按钮，拒绝点击')
                _log.warning('[决战] 确认弹窗未出现，重新识别并点击重置入口')

            _log.info('[决战] 识别到重置入口: {}', match_source)
            self._ctrl.click(*match.center)
            time.sleep(1.0)
            if ImageChecker.template_exists(
                self._ctrl.screenshot(),
                Templates.Build.SHIP_FULL_DEPOT,
                confidence=0.8,
            ):
                _log.warning('[决战] 重置章节时检测到船坞已满')
                return False
            try:
                confirm_operation(self._ctrl, must_confirm=True, timeout=5.0)
            except NavigationError:
                if attempt == 1:
                    raise
                continue
            time.sleep(1.0)
            return True

        raise TimeoutError('重置关卡确认失败')

    def navigate_to_chapter(self, target: int) -> None:
        """通过 OCR 和章节按钮导航到目标章节。

        Args:
            target: 目标章节编号，范围为 ``MIN_CHAPTER`` 到 ``MAX_CHAPTER``。

        Raises:
            ValueError: 目标章节超出决战章节范围。
            RuntimeError: 未注入 OCR 引擎。
            NavigationError: 多次尝试后仍无法到达目标章节。
        """
        from autowsgr.application.navigation.interaction import NavigationError

        if not MIN_CHAPTER <= target <= MAX_CHAPTER:
            raise ValueError(f'决战章节编号必须为 {MIN_CHAPTER}-{MAX_CHAPTER}，收到 {target}')
        if self._ocr is None:
            raise RuntimeError('navigate_to_chapter 需要 OCR 引擎')

        for attempt in range(_CHAPTER_NAV_MAX_ATTEMPTS):
            current = self.read_chapter()
            if current is None:
                _log.warning('[决战] 章节导航 OCR 失败，第 {} 次尝试', attempt + 1)
                time.sleep(_CHAPTER_SWITCH_DELAY)
                continue

            if current == target:
                _log.info('[决战] 已到达 Ex-{}', target)
                return
            if current > target:
                self.click_previous_chapter()
            else:
                self.click_next_chapter()

        raise NavigationError(
            f'决战章节导航失败：超过 {_CHAPTER_NAV_MAX_ATTEMPTS} 次尝试，目标 Ex-{target}',
            screen=self._ctrl.screenshot(),
        )

    # 页面回退。

    def go_back(self) -> None:
        """点击左上角返回按钮，回到母港主页。"""
        from autowsgr.application.controller.home import HomePage

        _log.info('[决战] 总览页 -> 母港主页')
        click_and_wait_for_page(
            self._ctrl,
            click_coord=CLICK_BACK,
            checker=HomePage.check_current_page,
            source=PageName.DECISIVE_BATTLE,
            target=PageName.HOME,
        )


__all__ = ['DecisiveBattlePage', 'DecisiveEntryPage']
