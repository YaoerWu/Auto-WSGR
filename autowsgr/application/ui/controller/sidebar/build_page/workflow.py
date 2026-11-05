"""

建造与解装的业务流程尚未迁移到新链路，当前不被任何模块导入；等第二阶段移植后恢复调用。模块功能：编排建造页面的建造流程和解装流程。上层调用：
- application.ui.controller.sidebar.build_page.page：调用建造和解装流程。

下层依赖：
- application.ui.controller.sidebar.build_page.constants：提供页面校准数据。
- application.ui.controller.sidebar.build_page.operations：执行原子页面点击。
- common.system.logger：提供模块日志。
- common.types：提供舰种枚举。
- common.vision、common.vision.resources：提供建造和确认状态识别。

本模块只编排建造页面内的多步骤流程，不负责页面导航、任务调度或业务配置读取。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.sidebar.build_page import constants, operations
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker


if TYPE_CHECKING:
    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import (
        ShipType,
    )
    from autowsgr.common.device.service import DeviceService


_log = get_logger('ui.sidebar.build_page.workflow')


# ── 建造流程参数 ─────────────────────────────────────────────────────────────

_BUILD_SLOT_COUNT = 4
_FAST_BUILD_TRANSITION_WAIT_SECONDS = 0.3
_COLLECT_RESULT_WAIT_SECONDS = 1.0
_BUILD_RESULT_ACTION_WAIT_SECONDS = 0.5
_BUILD_RESULT_MAX_PASSES = 10
_START_BUILD_TRANSITION_WAIT_SECONDS = 1.0
_RESOURCE_PAGE_TIMEOUT_SECONDS = 5.0
_RESOURCE_PAGE_POLL_INTERVAL_SECONDS = 0.3


# ── 解装流程参数 ─────────────────────────────────────────────────────────────

_DESTROY_STEP_WAIT_SECONDS = 1.5
_DESTROY_TYPE_WAIT_SECONDS = 0.8


# ── 主业务流程 ──────────────────────────────────────────────────────────────


def build(
    ctrl: DeviceService,
    *,
    build_count: int = 1,
    collect_completed: bool = True,
    build_type: str = 'ship',
    allow_fast_build: bool = False,
) -> int:
    """先收取已完成项目，再按数量执行新建造。

    Args:
        ctrl: 当前设备控制器。
        build_count: 要新建的数量，必须为非负整数。
        collect_completed: 是否先收取已完成的建造项目。
        build_type: 建造类型，`ship` 表示舰船，其他值表示装备。
        allow_fast_build: 是否先处理可快速建造的槽位。

    Returns:
        实际收取的数量。

    Raises:
        RuntimeError: 对应仓库已满、建造队列已满或资源页面未出现。
    """
    _log.info(
        '[UI] 建造页 → 建造：数量={}，先收取={}，类型={}，快速建造={}，状态=开始',
        build_count,
        '是' if collect_completed else '否',
        '舰船' if build_type == 'ship' else '装备',
        '是' if allow_fast_build else '否',
    )
    collected = 0
    collection_confirmed = not collect_completed

    if collect_completed:
        collected, collection_confirmed = _collect_completed(
            ctrl,
            build_type,
            allow_fast_build=allow_fast_build,
        )
    if build_count > 0:
        _start_builds(ctrl, build_type, build_count)

    _log.info(
        '[UI] 建造页 → 建造：数量={}，收取数量={}，结果={}',
        build_count,
        collected,
        '已提交' if build_count > 0 else ('成功' if collection_confirmed else '部分完成'),
    )
    return collected


def destroy_ships(
    ctrl: DeviceService,
    ship_types: list[ShipType] | None = None,
    *,
    remove_equipment: bool = True,
) -> None:
    """在解体标签上执行完整解装流程。

    Args:
        ctrl: 当前设备控制器。
        ship_types: 要解体的舰种列表；`None` 表示不过滤舰种。
        remove_equipment: 是否在解装前卸下装备。
    """
    selected_types = [ship_type.value for ship_type in ship_types] if ship_types else '全部'
    _log.info(
        '[UI] 解体页 → 解装：舰种={}，卸载装备={}，状态=开始',
        selected_types,
        '是' if remove_equipment else '否',
    )

    # 1. 打开解体列表。
    operations.click_destroy_add(ctrl)
    time.sleep(_DESTROY_STEP_WAIT_SECONDS)

    if ship_types:
        # 2. 应用舰种过滤条件。
        operations.click_destroy_type_filter(ctrl)
        time.sleep(_DESTROY_STEP_WAIT_SECONDS)
        for ship_type in ship_types:
            coordinate = constants.DESTROY_TYPE_POSITIONS[ship_type.name]
            _log.debug(
                '[UI] 解体页 → 选择舰种：舰种={!r}，坐标={!r}',
                ship_type.value,
                coordinate,
            )
            operations.click_destroy_type(ctrl, coordinate)
            time.sleep(_DESTROY_TYPE_WAIT_SECONDS)
        operations.click_destroy_confirm_filter(ctrl)
        time.sleep(_DESTROY_STEP_WAIT_SECONDS)

    # 3. 选择舰船并确认解装选项。
    operations.click_destroy_quick_select(ctrl)
    time.sleep(_DESTROY_STEP_WAIT_SECONDS)
    operations.click_destroy_confirm_select(ctrl)
    time.sleep(_DESTROY_STEP_WAIT_SECONDS)
    if remove_equipment:
        operations.click_destroy_remove_equipment(ctrl)
        time.sleep(_DESTROY_STEP_WAIT_SECONDS)

    # 4. 提交解装并确认高星舰船提示。
    operations.click_destroy_confirm(ctrl)
    time.sleep(_DESTROY_STEP_WAIT_SECONDS)
    operations.click_destroy_four_star(ctrl)
    time.sleep(_DESTROY_STEP_WAIT_SECONDS)

    _log.info(
        '[UI] 解体页 → 解装：舰种={}，卸载装备={}，结果=已提交',
        selected_types,
        '是' if remove_equipment else '否',
    )


# ── 建造收取子流程 ────────────────────────────────────────────────────────────


def _collect_completed(
    ctrl: DeviceService,
    build_type: str,
    *,
    allow_fast_build: bool,
) -> tuple[int, bool]:
    """收取当前页面上已完成的舰船或装备。

    Args:
        ctrl: 当前设备控制器。
        build_type: 建造类型，`ship` 表示舰船，其他值表示装备。
        allow_fast_build: 是否先处理可快速建造的槽位。

    Returns:
        实际收取的数量，以及结果浮层是否均已清理。

    Raises:
        RuntimeError: 对应仓库已满。
    """
    collected = 0
    collection_confirmed = True
    if allow_fast_build:
        fast_template = (
            Templates.Build.SHIP_FAST if build_type == 'ship' else Templates.Build.EQUIP_FAST
        )
        for slot_index in range(_BUILD_SLOT_COUNT):
            screen = ctrl.screenshot()
            detail = ImageChecker.find_template(screen, fast_template)
            if detail is None:
                break
            _log.debug(
                '[UI] 建造页 → 识别快建：槽位={}，中心坐标={!r}',
                slot_index + 1,
                detail.center,
            )
            operations.click_fast_build(ctrl, detail.center)
            time.sleep(_FAST_BUILD_TRANSITION_WAIT_SECONDS)
            screen = ctrl.screenshot()
            confirm = ImageChecker.find_any(screen, Templates.Confirm.all())
            _log.debug(
                '[UI] 建造页 → 判断确认：槽位={}，确认弹窗={!r}',
                slot_index + 1,
                confirm is not None,
            )
            if confirm is not None:
                operations.click_confirm_dialog(ctrl, confirm.center)
                time.sleep(_COLLECT_RESULT_WAIT_SECONDS)
            else:
                collection_confirmed = False
                _log.warning(
                    '[UI] 建造页 → 快建跳过：槽位={}，期望=确认弹窗，实际=缺失，'
                    '原因=未找到确认弹窗，下一步=普通收取，结果=继续',
                    slot_index + 1,
                )

    complete_template = (
        Templates.Build.SHIP_COMPLETE if build_type == 'ship' else Templates.Build.EQUIP_COMPLETE
    )
    full_depot_template = (
        Templates.Build.SHIP_FULL_DEPOT
        if build_type == 'ship'
        else Templates.Build.EQUIP_FULL_DEPOT
    )

    for slot_index in range(_BUILD_SLOT_COUNT):
        screen = ctrl.screenshot()
        detail = ImageChecker.find_template(screen, complete_template)
        if detail is None:
            break
        if ImageChecker.template_exists(screen, full_depot_template):
            _log.error(
                '[UI] 建造页 → 收取失败：类型={!r}，槽位={}，原因=仓库已满，结果=失败',
                build_type,
                slot_index + 1,
            )
            raise RuntimeError(f'{build_type} 仓库已满')
        operations.click_collect_slot(ctrl, detail.center)
        time.sleep(_COLLECT_RESULT_WAIT_SECONDS)
        if not _dismiss_build_result(ctrl):
            collection_confirmed = False
        collected += 1
    return collected, collection_confirmed


# ── 新建造子流程 ─────────────────────────────────────────────────────────────


def _start_builds(ctrl: DeviceService, build_type: str, build_count: int) -> None:
    """按数量执行新建造并确认资源选择页面。

    Args:
        ctrl: 当前设备控制器。
        build_type: 建造类型，`ship` 表示舰船，其他值表示装备。
        build_count: 要新建的数量。

    Raises:
        RuntimeError: 建造队列已满或资源页面未出现。
    """
    start_template = (
        Templates.Build.SHIP_START if build_type == 'ship' else Templates.Build.EQUIP_START
    )
    for build_index in range(build_count):
        screen = ctrl.screenshot()
        detail = ImageChecker.find_template(screen, start_template)
        if detail is None:
            _log.error(
                '[UI] 建造页 → 建造失败：类型={!r}，序号={}，总数={}，原因=建造队列已满，结果=失败',
                build_type,
                build_index + 1,
                build_count,
            )
            raise RuntimeError(f'{build_type} 建造队列已满')

        operations.click_start_build(ctrl, detail.center)
        time.sleep(_START_BUILD_TRANSITION_WAIT_SECONDS)

        deadline = time.monotonic() + _RESOURCE_PAGE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            screen = ctrl.screenshot()
            if ImageChecker.template_exists(screen, Templates.Build.RESOURCE):
                break
            time.sleep(_RESOURCE_PAGE_POLL_INTERVAL_SECONDS)
        else:
            _log.error(
                '[UI] 建造页 → 建造超时：类型={!r}，序号={}，总数={}，'
                '超时={:.1f}s，原因=资源选择页面未出现，结果=失败',
                build_type,
                build_index + 1,
                build_count,
                _RESOURCE_PAGE_TIMEOUT_SECONDS,
            )
            raise RuntimeError('资源选择页面未出现')

        operations.click_confirm_build(ctrl)
        time.sleep(_START_BUILD_TRANSITION_WAIT_SECONDS)


# ── 建造结果处理 ─────────────────────────────────────────────────────────────


def _dismiss_build_result(ctrl: DeviceService) -> bool:
    """清理建造结果浮层，直到页面可以继续操作。

    Args:
        ctrl: 当前设备控制器。

    Returns:
        结果浮层已清理时返回 True，达到处理上限仍未清理时返回 False。
    """
    result_templates = [Templates.Symbol.GET_SHIP, Templates.Symbol.GET_ITEM]
    for _ in range(_BUILD_RESULT_MAX_PASSES):
        screen = ctrl.screenshot()
        if not ImageChecker.template_exists(screen, result_templates):
            return True
        operations.click_dismiss_animation(ctrl)
        time.sleep(_BUILD_RESULT_ACTION_WAIT_SECONDS)
        screen = ctrl.screenshot()
        confirm = ImageChecker.find_any(screen, Templates.Confirm.all())
        if confirm is not None:
            operations.click_confirm_dialog(ctrl, confirm.center)
            time.sleep(_BUILD_RESULT_ACTION_WAIT_SECONDS)
    _log.warning(
        '[UI] 建造页 → 结果未清：处理次数={}，最大处理次数={}，'
        '期望=浮层已清理，实际=浮层仍存在，原因=达到最大处理次数，'
        '结果=继续，下一步=继续收取',
        _BUILD_RESULT_MAX_PASSES,
        _BUILD_RESULT_MAX_PASSES,
    )
    return False
