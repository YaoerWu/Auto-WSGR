"""模块功能：编排远征页面的通知检查、槽位收取和结算返回。

上层调用：
- business.logistics.expedition：调用远征收取完整流程。

下层依赖：
- application.ui.controller.operations.sortie_page.main_page：提供出征页页面检查和通知事实。
- application.ui.controller.operations.sortie_page.expedition_page.constants：提供槽位校准。
- application.ui.controller.operations.sortie_page.expedition_page.recognition：识别可收取槽位。
- application.ui.controller.operations.sortie_page.expedition_page.operations：执行槽位和结算点击。
- common.device.interaction：确认结算弹窗并等待地图终态。
- common.vision.resources：提供结算页模板。

本模块只持有远征收取的页面级流程，不决定跨任务调度或业务配置。
"""

from __future__ import annotations

import time

from autowsgr.application.controller.sortie import SortiePage
from autowsgr.application.ui.controller.operations.sortie_page.expedition_page import (
    constants,
    operations,
    recognition,
)
from autowsgr.application.navigation.interaction import (
    NavigationError,
    confirm_operation,
    wait_for_page,
)
from autowsgr.application.navigation.types import PageName
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker


_log = get_logger('ui.sortie.expedition_page')


# ── 收取流程参数 ─────────────────────────────────────────────────────────────

_MAX_COLLECTIONS = 8
_SLOT_REFRESH_TIMEOUT = 10.0
_SLOT_REFRESH_INTERVAL = 0.1
_SLOT_CLICK_SETTLE_DELAY = 1.0
_RESULT_PAGE_TIMEOUT = 5.0
_RESULT_PAGE_POLL_INTERVAL = 0.1
_RESULT_PAGE_SETTLE_DELAY = 0.25
_SKIP_SETTLE_DELAY = 1.0


class ExpeditionPage(SortiePage):
    """远征页面控制器，提供远征收取入口。"""

    def collect_expedition(self) -> int:  # noqa: PLR0912 - 页面总流程必须保留这些状态分支。
        """执行远征收取完整流程。

        Returns:
            本次收取的远征数量。

        Raises:
            NavigationError: 页面事实或结算终态无法确认。
        """
        collected = 0
        _log.info('[UI] 远征页 → 收取：状态=开始')

        for _ in range(_MAX_COLLECTIONS):
            # 1. 读取可收取槽位；通知仍在时等待槽位状态刷新。
            screen = self._ctrl.screenshot()
            slot_index = recognition.read_ready_expedition_slot(screen)
            if slot_index is None:
                notification = self.check_expedition_notification(screen)
                _log.debug(
                    '[UI] 远征页 → 判断收取：槽位索引={!r}，通知存在={!r}',
                    slot_index,
                    notification,
                )
                if not notification:
                    break

                deadline = time.monotonic() + _SLOT_REFRESH_TIMEOUT
                while True:
                    if time.monotonic() >= deadline:
                        _log.error(
                            '[UI] 远征页 → 超时：动作={!r}，期望={!r}，实际={!r}，'
                            '原因={!r}，错误类型={!r}，错误={!r}，结果=失败，下一步=抛出异常',
                            '等待就绪槽位',
                            '就绪槽位',
                            '未找到',
                            '通知仍然显示',
                            'NavigationError',
                            '就绪槽位等待超时',
                        )
                        raise NavigationError(
                            '远征收取超时：通知仍在但未检测到就绪槽位',
                            screen=screen,
                        )

                    time.sleep(_SLOT_REFRESH_INTERVAL)
                    screen = self._ctrl.screenshot()
                    slot_index = recognition.read_ready_expedition_slot(screen)
                    if slot_index is not None:
                        break
                    if not self.check_expedition_notification(screen):
                        _log.debug(
                            '[UI] 远征页 → 判断收取：槽位索引={!r}，通知存在={!r}',
                            slot_index,
                            False,
                        )
                        break

                if slot_index is None:
                    break

            slot_position = constants.SLOT_PROBES[slot_index]
            _log.info('[UI] 远征页 → 收取：槽位={}，状态=开始', slot_index + 1)
            operations.click_expedition_slot(self._ctrl, slot_position)
            time.sleep(_SLOT_CLICK_SETTLE_DELAY)

            # 2. 等待结算页确认后再跳过动画，避免误点击其他页面。
            result_found = False
            result_deadline = time.monotonic() + _RESULT_PAGE_TIMEOUT
            while True:
                screen = self._ctrl.screenshot()
                result_found = ImageChecker.template_exists(
                    screen,
                    Templates.Symbol.CLICK_TO_CONTINUE,
                )
                if result_found:
                    break
                if time.monotonic() >= result_deadline:
                    _log.error(
                        '[UI] 远征页 → 超时：动作={!r}，期望={!r}，实际={!r}，'
                        '原因={!r}，错误类型={!r}，错误={!r}，结果=失败，下一步=抛出异常',
                        '等待结算页',
                        '结算页',
                        '未找到',
                        '结算页等待超时',
                        'NavigationError',
                        '结算页未找到',
                    )
                    raise NavigationError('远征结算页未出现', screen=screen)
                time.sleep(_RESULT_PAGE_POLL_INTERVAL)

            time.sleep(_RESULT_PAGE_SETTLE_DELAY)
            operations.click_expedition_skip(self._ctrl)
            time.sleep(_SKIP_SETTLE_DELAY)

            # 3. 确认收取弹窗和地图页面终态。
            try:
                confirm_operation(
                    self._ctrl,
                    must_confirm=True,
                    delay=0.5,
                    confidence=0.9,
                    timeout=5.0,
                )
            except NavigationError as error:
                _log.opt(exception=True).error(
                    '[UI] 远征页 → 失败：动作={!r}，期望={!r}，实际={!r}，'
                    '原因={!r}，错误类型={!r}，错误={!r}，结果=失败，下一步=抛出异常',
                    '确认收取结果',
                    '确认弹窗',
                    '未找到',
                    '确认操作失败',
                    type(error).__name__,
                    str(error),
                )
                raise

            try:
                wait_for_page(
                    self._ctrl,
                    checker=self.check_current_page,
                    source='远征页',
                    target=PageName.SORTIE_MAP.value,
                )
            except NavigationError as error:
                _log.opt(exception=True).error(
                    '[UI] 远征页 → 失败：动作={!r}，期望={!r}，实际={!r}，'
                    '原因={!r}，错误类型={!r}，错误={!r}，结果=失败，下一步=抛出异常',
                    '返回地图',
                    '出征页面',
                    '未到达',
                    '页面未到达',
                    type(error).__name__,
                    str(error),
                )
                raise

            collected += 1
            _log.info(
                '[UI] 远征页 → 收取：槽位={}，结果=成功，数量={}',
                slot_index + 1,
                collected,
            )

        _log.info('[UI] 远征页 → 收取：结果=成功，数量={}', collected)
        return collected


__all__ = ['ExpeditionPage']
