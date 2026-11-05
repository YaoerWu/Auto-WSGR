"""模块功能：执行决战地图页的浮层、节点、出征、回退和节点修理操作。

上层调用：
- business.combat.decisive：驱动决战状态机并读取地图阶段。
- application.navigation：从决战准备页回到决战地图并继续导航。
- testing.ui、testing.ops：验证决战地图页面动作和恢复链路。

下层依赖：
- application.ui.controller.operations.sortie_page.decisive_page.constants：提供地图、浮层和识别校准。
- application.ui.controller.operations.sortie_page.decisive_page.overlay：识别浮层类型和页面状态。
- application.ui.controller.operations.sortie_page.decisive_page.recognition：执行战备舰队、节点和技能舰船 OCR。
- application.ui.controller.fleet：执行决战出征准备页动作。
- common.vision：提供截图、模板、像素和节点识别能力。

本控制器只负责决战地图页面操作；决战状态机的业务决策由上层负责。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import cv2

from autowsgr.application.navigation.interaction import (
    NavConfig,
    click_and_wait_for_page,
    confirm_operation,
)
from autowsgr.application.ui.controller.fleet import BattlePreparationPage, RepairStrategy
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    ADVANCE_CARD_POSITIONS,
    CLICK_ADVANCE_CONFIRM,
    CLICK_FLEET_CLOSE,
    CLICK_FLEET_REFRESH,
    CLICK_FORMATION,
    CLICK_LEAVE,
    CLICK_RETREAT_BUTTON,
    CLICK_RETREAT_CONFIRM,
    CLICK_SKILL,
    CLICK_SORTIE,
    SKILL_USED,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CLICK_CHOOSE_SHIP_BACK as _CLICK_CHOOSE_SHIP_BACK,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CLICK_MAP_BACK as _CLICK_MAP_BACK,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CLICK_REWARD_ACK as _REWARD_ACK_POSITION,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CLICK_USE_LAST_FLEET_CONFIRM as _USE_LAST_FLEET_CONFIRM,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    SHIP_HSV_HI as _SHIP_HSV_HI,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    SHIP_HSV_LO as _SHIP_HSV_LO,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    SHIP_MIN_AREA as _SHIP_MIN_AREA,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.overlay import (
    ADVANCE_CHOICE_ROI,
    ADVANCE_CHOICE_THREE_ROI,
    CONFIRM_EXIT_ROI,
    FLEET_ACQUISITION_ROI,
    FLEET_NAME_ROI,
    USE_LAST_FLEET_ROI,
    DecisiveOverlay,
    check_decisive_map_page,
    check_fleet_acquisition,
    detect_decisive_overlay,
    read_overlay_template,
    read_overlay_type,
)
from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.recognition import (
    read_available_ship_names,
    read_last_offer_name,
    read_ship_drop,
    read_skill_ship_names,
    recognize_fleet_options,
    recognize_map_node,
)
from autowsgr.application.vision.resources import Templates
from autowsgr.business.combat.decisive.types import DecisivePhase
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import (
    ROI,
    ImageChecker,
    PixelChecker,
    get_api_dll,
)


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.application.controller.types import ShipDamageState
    from autowsgr.application.ui.controller.context import UIContext as GameContext
    from autowsgr.business.combat.types import FleetSelection
    from autowsgr.config import DecisiveConfig


_log = get_logger('ui.decisive')


class DecisiveMapController:
    """决战地图页控制器。

    Args:
        ctx: 当前运行时 UI 上下文。
        config: 决战配置。
    """

    def __init__(
        self,
        ctx: GameContext,
        config: DecisiveConfig,
    ) -> None:
        """保存当前运行时上下文和决战配置。

        Args:
            ctx: 当前运行时 UI 上下文。
            config: 决战配置。
        """
        self._ctx = ctx
        self._ctrl = ctx.ctrl
        self._config = config
        self._ocr = ctx.ocr

    # 页面状态检测

    def check_current_page(self, screen: np.ndarray | None = None) -> bool:
        """判断截图是否为决战地图页 (无 overlay 遮挡)。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return check_decisive_map_page(screen)

    def check_skill_used(self) -> bool:
        """检查副官技能是否已经使用。"""
        screen = self._ctrl.screenshot()
        return PixelChecker.check_signature(screen, SKILL_USED).matched

    def check_fleet_overlay_open(self) -> bool:
        """当前是否仍停留在战备舰队获取界面。"""
        return check_fleet_acquisition(self._ctrl.screenshot())

    def check_dock_full(self) -> bool:
        """检查当前界面是否出现船坞已满提示。"""
        screen = self._ctrl.screenshot()
        return ImageChecker.template_exists(
            screen,
            Templates.Build.SHIP_FULL_DEPOT,
            confidence=0.8,
        )

    def read_overlay(self, screen: np.ndarray | None = None) -> DecisiveOverlay | None:
        """检测当前地图页上的 overlay 类型。"""
        if screen is None:
            screen = self._ctrl.screenshot()
        return read_overlay_type(screen)

    def read_decisive_phase(  # noqa: PLR0911, PLR0912
        self,
        screen: np.ndarray | None = None,
        *,
        advance_choice_roi: ROI | None = None,
        allow_fleet_overlay: bool = True,
    ) -> DecisivePhase | None:
        """单次截图检测当前决战页面状态。

        按以下优先级检测::

            1. dock_full      — 弹窗存活时间极短 (~2s)
            2. use_last_fleet — 进入已有进度章节时弹出
            3. overlay        — 战备舰队 / 前进点（必须先于地图页判断）
            4. 地图页         — 无 overlay 的正常决战地图页

        Returns:
        DecisivePhase | None
            检测到的阶段；过场动画中等未知状态返回 ``None``。
        """
        if screen is None:
            screen = self._ctrl.screenshot()

        if ImageChecker.template_exists(
            screen,
            Templates.Build.SHIP_FULL_DEPOT,
            confidence=0.8,
        ):
            _log.warning('[地图控制器] 检测到船坞已满弹窗')
            return DecisivePhase.DOCK_FULL

        if ImageChecker.template_exists(
            screen,
            Templates.Decisive.USE_LAST_FLEET,
            roi=USE_LAST_FLEET_ROI,
            confidence=0.8,
        ):
            _log.info('[地图控制器] 检测到「使用上次舰队」按钮')
            return DecisivePhase.USE_LAST_FLEET

        overlay = detect_decisive_overlay(
            screen,
            advance_choice_roi=advance_choice_roi,
            include_fleet_acquisition=allow_fleet_overlay,
        )
        if overlay is not None:
            if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                return DecisivePhase.ADVANCE_CHOICE
            if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                # A stale scrcpy frame can keep matching the acquisition title
                # after the overlay has already closed; confirm before OCR.
                time.sleep(0.2)
                fresh_screen = self._ctrl.screenshot()
                if check_fleet_acquisition(fresh_screen):
                    return DecisivePhase.CHOOSE_FLEET
                _log.debug('[地图控制器] 丢弃过期的战备舰队弹窗匹配')
            # Any other recognized overlay blocks map interaction. Let the
            # caller retry after it disappears instead of falling through to a
            # possibly stale map-page signature.
            return None

        if check_decisive_map_page(screen):
            # 进图后的首个稳定帧有时会短暂满足“地图页”特征，但战备舰队
            # overlay 会在随后 1-2 帧内出现。这里补一次短延迟复检，只把
            # 连续两次都稳定为地图页的结果视为 PREPARE_COMBAT。
            time.sleep(0.2)
            confirm_screen = self._ctrl.screenshot()

            overlay = detect_decisive_overlay(
                confirm_screen,
                advance_choice_roi=advance_choice_roi,
                include_fleet_acquisition=allow_fleet_overlay,
            )
            if overlay is not None:
                if overlay == DecisiveOverlay.ADVANCE_CHOICE:
                    _log.debug('[地图控制器] 地图页复检修正为 overlay: advance_choice')
                    return DecisivePhase.ADVANCE_CHOICE
                if overlay == DecisiveOverlay.FLEET_ACQUISITION:
                    if check_fleet_acquisition(confirm_screen):
                        _log.debug('[地图控制器] 地图页复检修正为 overlay: fleet_acquisition')
                        return DecisivePhase.CHOOSE_FLEET
                    _log.debug('[地图控制器] 地图页复检丢弃过期的战备舰队匹配')
                return None

            if check_decisive_map_page(confirm_screen):
                return DecisivePhase.PREPARE_COMBAT

        return None

    def _wait_for_use_last_fleet(self) -> bool:
        """等待总览稳定后，在固定按钮区域快速识别三次。"""
        time.sleep(3.0)
        for _ in range(3):
            if ImageChecker.template_exists(
                self._ctrl.screenshot(),
                Templates.Decisive.USE_LAST_FLEET,
                roi=USE_LAST_FLEET_ROI,
                confidence=0.8,
            ):
                return True
            time.sleep(0.2)
        return False

    def wait_for_entry_phase(
        self,
        *,
        wait_for_use_last: bool,
        wait_for_advance: bool,
        wait_for_fleet: bool = True,
        advance_choice_roi: ROI | None = None,
        timeout: float = 3.0,
        interval: float = 0.2,
    ) -> DecisivePhase:
        """通过分阶段正向识别解析进图后的下一个 UI 阶段。"""
        if wait_for_use_last and self._wait_for_use_last_fleet():
            return DecisivePhase.USE_LAST_FLEET

        if wait_for_advance and self._wait_for_advance_choice(
            advance_choice_roi,
            timeout=timeout,
            interval=interval,
        ):
            return DecisivePhase.ADVANCE_CHOICE

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            phase = self.read_decisive_phase(
                advance_choice_roi=advance_choice_roi,
                allow_fleet_overlay=wait_for_fleet,
            )
            if phase is not None:
                return phase
            time.sleep(interval)
        raise TimeoutError(f'决战进图阶段识别超时 ({timeout}s)')

    @staticmethod
    def _advance_choice_rois(advance_choice_roi: ROI | None) -> tuple[ROI, ...]:
        """返回地图分支和实机弹窗布局的候选 ROI。"""
        if advance_choice_roi is not None:
            return (advance_choice_roi, ADVANCE_CHOICE_ROI, ADVANCE_CHOICE_THREE_ROI)
        return (ADVANCE_CHOICE_ROI, ADVANCE_CHOICE_THREE_ROI)

    def _wait_for_advance_choice(
        self,
        advance_choice_roi: ROI | None,
        *,
        timeout: float,
        interval: float,
    ) -> bool:
        """在一个短窗口内确认前进点弹窗。"""
        deadline = time.monotonic() + timeout
        rois = self._advance_choice_rois(advance_choice_roi)
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if any(
                ImageChecker.template_exists(
                    screen,
                    Templates.Decisive.ADVANCE_CHOICE,
                    roi=roi,
                    confidence=0.80,
                )
                for roi in rois
            ):
                return True
            time.sleep(interval)
        return False

    # ── 舰船图标颜色检测参数 (HSV, BGR 输入) ──────────────────────

    def read_ship_icon_position(self) -> float | None:
        """读取当前地图舰船指示器的相对横坐标。

        Returns:
            舰船指示器的相对横坐标；战备舰队浮层出现时返回 ``-1``，
            未检测到指示器时返回 ``None``。
        """
        detect_screen = self._ctrl.screenshot()
        # 针对Ex5特调，A节点不选择分支，直接进入战备舰队获取
        screen_is_fleet_acquisition = check_fleet_acquisition(detect_screen)
        if screen_is_fleet_acquisition:
            return -1
        # _locate_ship_icon 需要 BGR；screenshot() 返回 RGB
        bgr = cv2.cvtColor(detect_screen, cv2.COLOR_RGB2BGR)
        icon_rel_x = self._locate_ship_icon(bgr)
        return icon_rel_x

    def read_ship_icon_position_with_retry(self) -> float | None:
        """等待舰船指示器出现并返回其相对横坐标。

        Returns:
            舰船指示器的相对横坐标、战备舰队浮层标记 ``-1`` 或 ``None``。
        """
        _icon_timeout = 10.0
        _icon_gap = 0.15
        deadline = time.monotonic() + _icon_timeout
        icon_rel_x: float | None = None
        while time.monotonic() < deadline:
            icon_rel_x = self.read_ship_icon_position()
            if icon_rel_x is not None:
                break
            time.sleep(_icon_gap)
        return icon_rel_x

    def read_node(
        self,
    ) -> str:
        """DLL 识别当前决战节点字母 (如 ``'A'``, ``'B'``)。

        算法 (无模板依赖):

        1. 轮询截图，通过 **HSV 颜色分割** 定位舰船指示器 X 坐标
           (地图上最大的橙黄色连通区域)。
        2. 以舰标 X 为参考裁剪全高竖列，送 DLL ``recognize_map`` 识别。
        3. DLL 返回 ``'0'`` 时重试 (最多 3 次)，全部失败抛出异常。
        """
        _max_retry = 3
        dll = get_api_dll()

        for retry in range(_max_retry + 1):
            icon_rel_x: float | None = self.read_ship_icon_position_with_retry()
            for retry_icon in range(_max_retry + 1):
                time.sleep(0.5)
                icon_rel_x_now = self.read_ship_icon_position_with_retry()
                if icon_rel_x_now == -1:
                    return 'CHOOSE_FLEET'
                if icon_rel_x_now == icon_rel_x:
                    _log.debug('[地图控制器] 舰船指示器位置: X={}', icon_rel_x)
                    break
                _log.debug(
                    '[地图控制器] 舰船指示器位置偏移, 重试{:d}: X1={}, X2={}',
                    retry_icon,
                    icon_rel_x,
                    icon_rel_x_now,
                )
                icon_rel_x = icon_rel_x_now

            if icon_rel_x is None:
                raise RuntimeError('决战节点识别失败: 舰船指示器超时未出现')

            # 2. 取新截图，按舰标 X 裁剪竖列
            fresh_screen = self._ctrl.screenshot()

            # 3. DLL 识别
            try:
                result = recognize_map_node(dll, fresh_screen, icon_rel_x)
                if result != '0':
                    _log.info('[地图控制器] 识别决战节点: {}', result[0])
                    return result[0]
            except Exception:
                _log.warning('[地图控制器] DLL 节点识别异常', exc_info=True)

            if retry >= _max_retry:
                break
            _log.warning(
                '[地图控制器] 节点识别失败, 正在重试第 {} 次',
                retry + 1,
            )

        raise RuntimeError(f'决战节点识别失败: 重试 {_max_retry + 1} 次后仍无法识别')

    # 战备舰队获取 overlay

    def read_fleet_options(
        self,
        screen: np.ndarray | None = None,
        fallback_score: int | None = None,
    ) -> tuple[int, dict[str, FleetSelection]]:
        """读取战备舰队获取浮层中的可购买选项。

        Args:
            screen: 可选的稳定 RGB 截图；未提供时等待浮层稳定。
            fallback_score: 分数 OCR 失败时使用的上一轮分数。

        Returns:
            当前可用分数和可购买舰船选项。
        """
        if screen is None:
            screen = self.wait_for_fleet_overlay_stable()
        return recognize_fleet_options(
            self._ocr,
            screen,
            fallback_score=fallback_score,
        )

    def wait_for_fleet_overlay_stable(
        self,
        screen: np.ndarray | None = None,
        timeout: float = 8.0,
    ) -> np.ndarray:
        """等待战备舰队弹窗稳定后返回截图。

        当上层已通过阶段纠偏进入 ``CHOOSE_FLEET`` 时，当前截图本身就可能是
        首进购买界面，此时不要再次强依赖旧的 overlay 像素签名；直接以当前截图
        为起点做短暂稳定等待即可。
        """
        if screen is None:
            screen = self.wait_for_overlay(DecisiveOverlay.FLEET_ACQUISITION, timeout=timeout)

        stable_deadline = time.monotonic() + 1.0
        last_screen = screen
        while time.monotonic() < stable_deadline:
            time.sleep(0.25)
            last_screen = self._ctrl.screenshot()
        return last_screen

    def read_last_offer_name(
        self,
        screen: np.ndarray | None = None,
    ) -> str | None:
        """读取战备舰队最后一张卡片的名称。

        Args:
            screen: 可选的稳定 RGB 截图；未提供时读取当前截图。

        Returns:
            最后一张卡片的舰船名称；无法识别时返回 ``None``。
        """
        if screen is None:
            screen = self._ctrl.screenshot()
        return read_last_offer_name(self._ocr, screen)

    def buy_fleet_option(self, click_position: tuple[float, float]) -> None:
        """点击购买一个舰船或技能卡片。

        Args:
            click_position: 卡片购买按钮的归一化坐标。
        """
        self._ctrl.click(*click_position)
        time.sleep(0.3)

    def refresh_fleet(self) -> None:
        """点击「刷新」按钮，刷新备选舰船。"""
        self._ctrl.click(*CLICK_FLEET_REFRESH)
        time.sleep(1.5)

    def close_fleet_overlay(self) -> bool:
        """关闭战备舰队获取 overlay，并确认已离开该弹窗。"""
        if not self.check_fleet_overlay_open():
            _log.warning('[地图控制器] 关闭战备舰队前未确认弹窗仍存在')
            return False
        self._ctrl.click(*CLICK_FLEET_CLOSE)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            screen = self._ctrl.screenshot()
            if not check_fleet_acquisition(screen):
                return True
            time.sleep(0.2)
        _log.warning('[地图控制器] 关闭战备舰队弹窗后仍停留在原界面')
        return False

    def click_use_last_fleet(self) -> None:
        """单次尝试点击「使用上次舰队」按钮并确认。

        对应 Legacy ``decisive_battle_image[7]`` + ``click(873, 500)``。
        由状态机多次调度实现重试。
        """
        deadline = time.monotonic() + 5.0
        match = None
        while time.monotonic() < deadline:
            match = ImageChecker.find_template(
                self._ctrl.screenshot(),
                Templates.Decisive.USE_LAST_FLEET,
                roi=USE_LAST_FLEET_ROI,
                confidence=0.8,
            )
            if match is not None:
                break
            time.sleep(0.2)
        if match is None:
            raise TimeoutError('未识别到「使用上次舰队」按钮，拒绝点击')

        self._ctrl.click(*match.center)
        time.sleep(0.5)
        self._ctrl.click(*_USE_LAST_FLEET_CONFIRM)
        time.sleep(1.0)

    def use_skill(self) -> list[str]:
        """点击一次副官技能并返回技能浮层中识别到的舰船。"""
        self._ctrl.click(*CLICK_SKILL)
        time.sleep(1.0)
        acquired = read_skill_ship_names(self._ocr, self._ctrl.screenshot())
        self._ctrl.click(*CLICK_SKILL)
        return acquired

    def read_fleet(
        self,
        *,
        scan_ship_pool: bool = False,
    ) -> tuple[list[str | None], dict[int, ShipDamageState], set[str]]:
        """恢复进度时在编队页面扫描当前编队及所有可用舰船。

        完整 UI 流程:

        1. 进入编队页 (preparation page)
        2. OCR 识别当前编队成员 + 像素检测血量
        3. 可选：进入选船列表扫描所有可用舰船
        4. 扫描完成后停留在准备页，供调用方继续调整或出征

        对齐 legacy ``_check_fleet``: 同时收集编队成员与列表中的舰船。

        Returns:
        tuple[list[str | None], dict[int, ShipDamageState], set[str]]
            ``(fleet, damage, all_ships)``:

            - *fleet*: 当前 6 槽位舰船名 (``None`` 为空)
            - *damage*: 各槽位血量状态
            - *all_ships*: 所有可用舰船名 (含编队成员)
        """
        _log.info('[地图控制器] 扫描当前编队与可用舰船')

        self.enter_formation()
        time.sleep(0.5)  # 等待编队页加载完成
        page = BattlePreparationPage(self._ctx)

        screen = self._ctrl.screenshot()
        fleet_snapshot = page.read_fleet_snapshot(recognize_ship_types=False)
        fleet = fleet_snapshot.names
        damage = page.read_ship_damage(screen)

        current_ships = {name for name in fleet if name}
        if current_ships and not scan_ship_pool:
            _log.info('[地图控制器] 当前编队非空，跳过选船池扫描')
            return fleet, damage, current_ships

        # 进入选船列表：先确认已离开出征准备页，再进行一次识别
        page.click_ship_slot(0)
        deadline = time.monotonic() + 5.0
        ship_list_screen = None
        while time.monotonic() < deadline:
            time.sleep(0.2)
            screen = self._ctrl.screenshot()
            if not BattlePreparationPage.check_current_page(screen):
                ship_list_screen = screen
                break

        if ship_list_screen is None:
            raise TimeoutError('点击舰船位后未确认进入选船列表，拒绝继续扫描')
        else:
            time.sleep(0.3)  # 等待选船列表内容稳定
            ship_list_screen = self._ctrl.screenshot()

        available = read_available_ship_names(self._ocr, ship_list_screen)
        _log.debug('[地图控制器] 选船列表识别结果: {}', sorted(available))

        # 编队中的舰船也计入可用集合
        all_ships = set(available)
        for name in fleet:
            if name is not None:
                all_ships.add(name)

        # 返回准备页
        self._ctrl.click(*_CLICK_CHOOSE_SHIP_BACK)
        time.sleep(1.0)

        _log.info(
            '[地图控制器] 编队={}, 可用舰船={}',
            fleet,
            sorted(all_ships),
        )
        return fleet, damage, all_ships

    # 选择前进点 overlay

    def select_advance_card(
        self,
        index: int,
        *,
        advance_choice_roi: ROI | None = None,
    ) -> None:
        """选择前进点卡片并确认路线。

        Args:
            index: 前进卡片在当前浮层中的索引。
        """
        if not 0 <= index < len(ADVANCE_CARD_POSITIONS):
            raise ValueError(f'前进卡片索引无效: {index}')
        self.wait_for_overlay(
            DecisiveOverlay.ADVANCE_CHOICE,
            timeout=5.0,
            interval=0.2,
            advance_choice_roi=advance_choice_roi,
        )
        self._ctrl.click(*ADVANCE_CARD_POSITIONS[index])
        time.sleep(0.5)
        self._ctrl.click(*CLICK_ADVANCE_CONFIRM)
        time.sleep(1.5)

    # 地图操作

    def enter_formation(self) -> None:
        """点击右下角「编队」按钮。"""
        time.sleep(1)
        screen = self._ctrl.screenshot()
        if not check_decisive_map_page(screen):
            _log.warning('[地图控制器] 点击编队前未识别到决战地图页，拒绝点击')
            raise TimeoutError('点击编队前未识别到决战地图页')

        map_check = ImageChecker.template_exists(
            screen, Templates.Decisive.MAP_PAGE, confidence=0.85
        )
        prep_check = ImageChecker.template_exists(
            screen, Templates.Page.BATTLE_PREP, confidence=0.85
        )
        _log.debug(
            '[地图控制器] 点击编队前 - 地图页: {}, 出征准备页: {}',
            map_check,
            prep_check,
        )

        config = NavConfig(timeout=10.0, interval=0.5, max_retries=3)
        for attempt in range(2):
            click_and_wait_for_page(
                self._ctrl,
                CLICK_FORMATION,
                BattlePreparationPage.check_current_page,
                config=config,
                source='决战地图',
                target='出征准备',
            )
            if self._wait_for_fleet_name():
                return
            if attempt == 0:
                _log.warning('[地图控制器] 出征准备页未识别到决战舰队标题，返回地图后重试')
                self.navigate_to_map_page()
                time.sleep(0.5)

        raise TimeoutError('进入决战出征准备页后未识别到「主力决战舰队」标题')

    def _wait_for_fleet_name(self) -> bool:
        """在固定 ROI 内确认决战编队标题。"""
        for _ in range(3):
            if ImageChecker.template_exists(
                self._ctrl.screenshot(),
                Templates.Decisive.FLEET_NAME,
                roi=FLEET_NAME_ROI,
                confidence=0.8,
            ):
                return True
            time.sleep(0.2)
        return False

    def click_sortie(self) -> None:
        """点击右下角「出征」按钮。"""
        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

    def navigate_to_map_page(self) -> None:
        """确保当前在决战地图页（若在准备页则点击左上角返回）。"""
        screen = self._ctrl.screenshot()
        if check_decisive_map_page(screen):
            return
        self._ctrl.click(*_CLICK_MAP_BACK)
        time.sleep(1.0)
        if not check_decisive_map_page(self._ctrl.screenshot()):
            _log.warning('[地图控制器] 无法确认已回到地图页')

    def open_retreat_dialog(self) -> None:
        """点击左上角撤退按钮，打开确认退出 overlay。"""
        self.navigate_to_map_page()
        self._ctrl.click(*CLICK_RETREAT_BUTTON)
        time.sleep(1.0)
        self.wait_for_overlay(DecisiveOverlay.CONFIRM_EXIT, timeout=5.0)

    def confirm_retreat(self) -> None:
        """在确认退出 overlay 中点击「撤退」。"""
        self._ctrl.click(*CLICK_RETREAT_CONFIRM)
        time.sleep(2.0)

    def confirm_leave(self) -> None:
        """在确认退出 overlay 中点击「暂离」。"""
        self._ctrl.click(*CLICK_LEAVE)
        time.sleep(2.0)

    def confirm_stage_clear(self) -> list[str]:  # noqa: PLR0912
        """小关通关后确认弹窗并收集掉落舰船。"""
        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0, delay=2.0)
        confirm_operation(self._ctrl, must_confirm=True, timeout=5.0, delay=2.0)

        ship_templates = [
            Templates.Symbol.GET_SHIP,
            Templates.Symbol.GET_ITEM,
        ]
        entry_templates = Templates.Decisive.entry_status_templates()
        collected: list[str] = []
        for _ in range(10):
            # 等待掉落弹窗出现
            if ImageChecker.template_exists(
                self._ctrl.screenshot(),
                ship_templates,
                confidence=0.8,
            ):
                break
            time.sleep(0.25)
        while True:
            screen = self._ctrl.screenshot()
            detail = ImageChecker.find_any(
                screen,
                ship_templates,
                confidence=0.8,
            )
            if detail is None:
                time.sleep(1.0)
                screen = self._ctrl.screenshot()
                detail = ImageChecker.find_any(
                    screen,
                    ship_templates,
                    confidence=0.8,
                )
                if detail is None:
                    break

            ship_drop = read_ship_drop(self._ocr, screen)
            _log.info(f'[地图控制器] 检测到掉落: {ship_drop.ship_name}({ship_drop.ship_type})')
            collected.append(ship_drop.ship_name)
            self._ctrl.click(*_REWARD_ACK_POSITION)
            time.sleep(0.5)
            confirm_operation(self._ctrl, timeout=1.0)

        # 掉落处理结束后，继续等待回到决战入口页，避免奖励弹窗残留导致后续状态识别超时
        settle_deadline = time.monotonic() + 12.0
        while time.monotonic() < settle_deadline:
            screen = self._ctrl.screenshot()
            if ImageChecker.find_any(screen, entry_templates, confidence=0.8) is not None:
                _log.info('[地图控制器] 小关通关结算完成，已回到决战入口页')
                break

            reward_detail = ImageChecker.find_any(screen, ship_templates, confidence=0.8)
            if reward_detail is not None:
                _log.info("[地图控制器] 结算阶段仍有奖励弹窗: '{}'", reward_detail.template_name)
                self._ctrl.click(*_REWARD_ACK_POSITION)
                time.sleep(0.35)
                confirm_operation(self._ctrl, timeout=0.8)
                confirm_operation(self._ctrl, timeout=0.8)
                continue

            if confirm_operation(self._ctrl, timeout=0.8):
                continue

            time.sleep(0.3)
        else:
            _log.warning('[地图控制器] 小关通关后未能确认已回到决战入口页')

        # settle 循环结束后，如果仍未回到入口页，尝试从地图页返回
        for _ in range(5):
            screen = self._ctrl.screenshot()
            if ImageChecker.find_any(screen, entry_templates, confidence=0.8) is not None:
                _log.info('[地图控制器] 通过返回按钮回到决战入口页')
                break
            _log.debug('[地图控制器] 尝试点击返回按钮回到决战入口页')
            self._ctrl.click(*_CLICK_MAP_BACK)
            time.sleep(1.0)
        else:
            _log.warning('[地图控制器] 多次尝试后仍未能回到决战入口页')

        if collected:
            _log.info('[地图控制器] 小关通关共收集 {} 个掉落', len(collected))
        return collected

    # 节点间修理

    def repair_at_node(self, repair_level: int) -> list[int]:
        """进入出征准备页 → 执行快速修理 → 返回地图页。"""
        _log.info('[地图控制器] 节点间修理 (等级: {})', repair_level)

        self._ctrl.click(*CLICK_SORTIE)
        time.sleep(2.0)

        page = BattlePreparationPage(self._ctx)
        strategy = RepairStrategy.MODERATE if repair_level <= 1 else RepairStrategy.SEVERE
        repaired = page.apply_repair(strategy)

        if repaired:
            _log.info('[地图控制器] 修理完成, 修理槽位: {}', repaired)
        else:
            _log.debug('[地图控制器] 无需修理')

        page.go_back()
        time.sleep(1.0)
        return repaired

    def change_fleet(
        self,
        ship_names: list[str | None],
    ) -> None:
        """进入出征准备页 → 执行决战专用换船 → 保持在准备页。

        使用统一准备页的 ``task_type='decisive'`` 分支
        执行换船，原理是 OCR 选船列表直接点击目标，无需输入搜索框。

        Args:
        ship_names:
            目标舰船名列表 (按槽位 0-5)；``None``/``""`` 表示该位留空。
        """
        _log.info('[地图控制器] 进入准备页换船: {}', ship_names)
        page = BattlePreparationPage(self._ctx)
        page.adjust_fleet(
            fleet_id=None,
            fleet_rules=ship_names,
            task_type='decisive',
        )

    # 等待方法

    def wait_for_overlay(
        self,
        target: DecisiveOverlay,
        timeout: float = 5.0,
        interval: float = 0.3,
        *,
        advance_choice_roi: ROI | None = None,
    ) -> np.ndarray:
        """等待指定决战浮层出现并返回稳定截图。

        Args:
            target: 需要等待的浮层类型。
            timeout: 最长等待时间，单位为秒。
            interval: 截图检查间隔，单位为秒。

        Returns:
            匹配到浮层时的 RGB 截图。

        Raises:
            TimeoutError: 超时仍未匹配到目标浮层。
        """
        tmpl = read_overlay_template(target)
        confidence = (
            0.70
            if target is DecisiveOverlay.FLEET_ACQUISITION
            else 0.80
            if target is DecisiveOverlay.ADVANCE_CHOICE
            else 0.85
        )
        deadline = time.monotonic() + timeout
        while True:
            screen = self._ctrl.screenshot()
            if target is DecisiveOverlay.ADVANCE_CHOICE:
                rois = self._advance_choice_rois(advance_choice_roi)
                matched = any(
                    ImageChecker.template_exists(
                        screen,
                        tmpl,
                        roi=roi,
                        confidence=confidence,
                    )
                    for roi in rois
                )
            else:
                roi = (
                    FLEET_ACQUISITION_ROI
                    if target is DecisiveOverlay.FLEET_ACQUISITION
                    else CONFIRM_EXIT_ROI
                    if target is DecisiveOverlay.CONFIRM_EXIT
                    else None
                )
                matched = ImageChecker.template_exists(
                    screen,
                    tmpl,
                    roi=roi,
                    confidence=confidence,
                )
            if matched:
                return screen
            if time.monotonic() >= deadline:
                raise TimeoutError(f'等待 overlay {target.value} 超时 ({timeout}s)')
            time.sleep(interval)

    # 私有视觉辅助。
    @staticmethod
    def _locate_ship_icon(bgr: np.ndarray) -> float | None:
        """通过 HSV 颜色分割定位舰船指示器的 **相对** X 中心。

        不依赖任何图像模板，仅利用舰船指示器在决战地图上独特的
        橙黄色高亮面积远大于其它同色碎片这一视觉特征。

        Returns:
        float | None
            舰标中心 X 占图像宽度比例 (0-1)；检测失败返回 ``None``。
        """
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, _SHIP_HSV_LO, _SHIP_HSV_HI)
        # 闭运算连接临近像素
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        n_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
        if n_labels < 2:
            return None

        # 跳过背景 (label 0)，取面积最大的连通区域
        areas = stats[1:, cv2.CC_STAT_AREA]
        best = int(areas.argmax()) + 1
        if stats[best, cv2.CC_STAT_AREA] < _SHIP_MIN_AREA:
            return None
        return float(centroids[best][0]) / bgr.shape[1]


__all__ = ['DecisiveMapController']
