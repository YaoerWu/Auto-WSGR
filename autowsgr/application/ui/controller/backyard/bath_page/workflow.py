"""模块功能：暂存浴室的修理流程，尚未迁移到新链路。

上层调用：
- 暂无。本模块是旧 page.py 里修理流程的暂存位置，等第二阶段迁移到新链路后由 page.py 调用。

下层依赖：
- bath_page.constants / operations / recognition：提供坐标、原子点击与页面事实；
- common.device.interaction 的旧 wait_for_page：提供浮层到达等待。

边界：暂存代码，不接进导航器。它依赖的若干旧模块已随架构升级删除，
因此本模块当前无法导入；迁移到新链路后这些依赖会被换掉。
"""

from __future__ import annotations

import time

from autowsgr.application.ui.controller.backyard.bath_page import constants, operations, recognition
from autowsgr.application.navigation.types import NavigationError
from autowsgr.common.device.interaction import wait_for_page
from autowsgr.common.system.logger import get_logger


_log = get_logger('ui.bath_page')


# ── 修理流程参数 ─────────────────────────────────────────────────────────────

_OVERLAY_CLOSE_TIMEOUT = 10.0  # 浮层关闭终态的最长等待时间（秒）。
_REPAIR_RESULT_TIMEOUT = 3.0  # 单艘舰船修理结果的最长确认时间（秒）。
_REPAIR_ALL_SETTLE_DELAY = 1.0  # 全部修理点击后的页面稳定等待时间（秒）。
_REPAIR_ALL_TIMEOUT = 10.0  # 全部修理后的浮层终态确认上限（秒）。
_REPAIR_ALL_POLL_INTERVAL = 0.5  # 全部修理终态轮询间隔（秒）。
_MAX_REPAIR_PAGES = 10  # 单次修理流程最多扫描的列表页数。
_MAX_VISIBLE_REPAIR_CARDS = 5  # 单页完整可见卡片数，用于判断列表是否到末尾。


RepairResult = None | int | tuple[str, int]
"""浴室修理流程的统一结果。"""


# ── 修理流程 ────────────────────────────────────────────────────────────────


def repair(  # noqa: C901, PLR0911, PLR0912
    self,
    *,
    repair_all: bool,
    ship_name: str | None = None,
    blacklist: set[str] | None = None,
) -> RepairResult:
    """打开修理浮层，并根据入参完成全部或手动修理。

    Args:
        repair_all: 为 True 时提交全部修理；为 False 时执行手动选择流程。
        ship_name: 手动流程指定的舰船名称；为空时选择耗时最长的候选。
        blacklist: 未指定舰船时排除的舰船名称集合。

    Returns:
        全部修理返回 None；指定舰船返回修理秒数；自动选择候选时返回舰船名和秒数。

    Raises:
        NavigationError: 无法打开浮层或未能确认修理终态。
        LookupError: 指定舰船不在修理列表中。
        ValueError: 修理参数组合不合法。
    """
    if repair_all and (ship_name is not None or blacklist is not None):
        raise ValueError('全部修理不能同时指定舰船或黑名单')
    if not repair_all and ship_name is not None and blacklist is not None:
        raise ValueError('指定舰船修理不能同时指定黑名单')

    ctrl = self._ctrl

    # 1. 点击右上角入口并确认选择修理浮层出现。
    if not recognition.check_choose_repair_overlay(ctrl.screenshot()):
        operations.click_choose_repair(ctrl)
    wait_for_page(
        ctrl,
        recognition.check_choose_repair_overlay,
        source='浴室',
        target='选择修理浮层',
    )
    _log.info('[UI] 浴室 → 打开选择修理浮层：结果=成功')

    # 2. 全部修理分支。
    if repair_all:
        screen = ctrl.screenshot()
        if not recognition.check_repair_all_available(screen):
            operations.click_repair_card(ctrl, constants.CLICK_FIRST_REPAIR_SHIP)
            if not operations.wait_overlay_closed(
                ctrl,
                checker=lambda frame: recognition.check_current_page(frame).matched,
                overlay_checker=recognition.check_choose_repair_overlay,
                timeout=_REPAIR_RESULT_TIMEOUT,
            ):
                raise NavigationError(
                    '选择修理浮层未关闭，无法确认修理结果',
                    screen=ctrl.screenshot(),
                )
            _log.info('[UI] 选择修理浮层 → 修理首艘舰船：结果=成功')
            return None

        _log.info('[UI] 选择修理浮层 → 点击全部修理：状态=开始')
        operations.click_repair_all(ctrl)
        time.sleep(_REPAIR_ALL_SETTLE_DELAY)
        deadline = time.monotonic() + _REPAIR_ALL_TIMEOUT
        while time.monotonic() < deadline:
            screen = ctrl.screenshot()
            if recognition.check_current_page(
                screen
            ).matched and not recognition.check_choose_repair_overlay(screen):
                _log.info('[UI] 选择修理浮层 → 全部修理：结果=成功')
                return None

            if recognition.check_close_overlay_available(screen):
                _log.warning(
                    '[UI] 选择修理浮层 → 手动收尾：原因={!r}，下一步={!r}',
                    '浮层仍然打开',
                    '关闭浮层',
                )
                operations.click_close_overlay(ctrl)
                if not operations.wait_overlay_closed(
                    ctrl,
                    checker=lambda frame: recognition.check_current_page(frame).matched,
                    overlay_checker=recognition.check_choose_repair_overlay,
                    timeout=_REPAIR_RESULT_TIMEOUT,
                ):
                    raise NavigationError(
                        '全部修理后手动关闭浮层失败',
                        screen=ctrl.screenshot(),
                    )
                _log.info('[UI] 选择修理浮层 → 全部修理：结果=成功')
                return None

            time.sleep(_REPAIR_ALL_POLL_INTERVAL)

        raise NavigationError('全部修理后浮层未关闭', screen=ctrl.screenshot())

    # 3. 手动分支：指定舰船，或从候选中选择修理时间最长者。
    blocked = set(blacklist or ())
    for attempt in range(_MAX_REPAIR_PAGES):
        if self._ctx.ocr is None:
            raise RuntimeError('浴室修理需要 OCR 引擎')
        ships = recognition.recognize_repair_cards(ctrl.screenshot(), self._ctx.ocr)
        target = next((ship for ship in ships if ship.name == ship_name), None)
        if ship_name is None:
            candidates = [ship for ship in ships if ship.name and ship.name not in blocked]
            target = (
                max(
                    candidates,
                    key=lambda ship: recognition.convert_repair_time_to_seconds(ship.repair_time),
                )
                if candidates
                else None
            )

        if target is not None:
            repair_seconds = recognition.convert_repair_time_to_seconds(target.repair_time)
            _log.info(
                '[UI] 选择修理浮层 → 选择舰船：舰船={!r}，修理时间={!r}，状态=开始',
                target.name,
                target.repair_time,
            )
            operations.click_repair_card(ctrl, target.position)
            closed = operations.wait_overlay_closed(
                ctrl,
                checker=lambda frame: recognition.check_current_page(frame).matched,
                overlay_checker=recognition.check_choose_repair_overlay,
                timeout=_REPAIR_RESULT_TIMEOUT,
            )
            if closed:
                _log.info(
                    '[UI] 选择修理浮层 → 修理成功：舰船={!r}，修理秒数={}',
                    target.name,
                    repair_seconds,
                )
                if ship_name is None:
                    return target.name, repair_seconds
                return repair_seconds

            _log.warning(
                '[UI] 选择修理浮层 → 修理失败：舰船={!r}，原因={!r}，结果=失败',
                target.name,
                '浴室已满',
            )
            if ship_name is None:
                return '', -2
            return -1

        if len(ships) < _MAX_VISIBLE_REPAIR_CARDS:
            break
        if attempt == _MAX_REPAIR_PAGES - 1:
            break
        operations.swipe_repair_list(ctrl)

    if ship_name is not None:
        raise LookupError(f'选择修理浮层中未找到舰船 "{ship_name}"')
    _log.info('[UI] 选择修理浮层 → 无可修舰船：结果=未找到')
    return '', -1
