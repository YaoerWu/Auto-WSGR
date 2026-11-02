"""模块功能：在出征准备页执行舰队成员替换、清理和位置排序。

上层调用：
- formation.fleet_adjustment.workflow：调用成员调整和排序。
- formation.fleet_adjustment.campaign：复用固定槽位操作。

下层依赖：
- formation.fleet_adjustment.rules、planning：提供规则和槽位计算。
- formation.ship_selection：提供选船页面操作。
- main_page.constants：提供准备页舰船槽位坐标。
- common.constants：提供舰名身份比较。

本模块只编排已确定的目标和候选，不决定 OCR 生命周期或业务任务调度。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.fleet_adjustment import (
    constants,
    planning,
    rules,
)
from autowsgr.application.ui.controller.fleet.formation.ship_selection import workflow
from autowsgr.application.ui.controller.fleet.main_page.constants import CLICK_SHIP_SLOT
from autowsgr.application.fleet_select.names import ship_name_identity
from autowsgr.business.combat.fleet_models import ShipSelector
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.ui.controller.context import UIContext
    from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import (
        FleetSnapshot,
    )
    from autowsgr.application.ui.controller.fleet.main_page import BattlePreparationPage
    from autowsgr.business.combat.fleet_models import FleetSlotRule


_log = get_logger('ui.fleet.formation.fleet_adjustment')


class _UnresolvedPrimaryError(RuntimeError):
    """连续 OCR 后仍无法确认唯一主选时终止本次换船。"""


@dataclass(frozen=True, slots=True)
class _ShipSelection:
    """记录一次选船尝试的实际名称和规则。"""

    name: str | None
    option: ShipSelector | None


class FleetAlignment:
    """执行一次编队调整中的成员替换、清理和排序。"""

    def __init__(
        self,
        ctx: UIContext,
        page: BattlePreparationPage,
        *,
        use_search: bool,
        on_event: Callable[..., None] | None = None,
    ) -> None:
        """保存本次调整使用的上下文、页面和模式分支。"""
        self._ctx = ctx
        self._page = page
        self._ctrl = ctx.ctrl
        self._use_search = use_search
        self._on_fleet_event = on_event
        self._planner = planning.FleetPlanner()

    def _emit_fleet_event(self, event: str, **data: object) -> None:
        """向上层报告已经完成的编队动作。"""
        if self._on_fleet_event is not None:
            self._on_fleet_event(event, **data)

    def _try_select_option(self, slot: int, option: ShipSelector) -> _ShipSelection:
        """在指定槽位尝试一条选船规则。"""
        selected = workflow.select_ship(
            self._ctx,
            self._page,
            slot,
            (option,),
            use_search=self._use_search,
        )
        return _ShipSelection(name=selected, option=option)

    def _change_single_ship(
        self,
        slot: int,
        name: str | None,
        *,
        selector: Sequence[ShipSelector] | None = None,
        slot_occupied: bool = True,
    ) -> str | None:
        """按有序规则更换或移除指定物理槽位的舰船。"""
        if name is None and not slot_occupied:
            return None
        if name is None:
            workflow.remove_ship(self._ctx, self._page, slot)
            self._emit_fleet_event('ship_removed', slot=slot + 1, selected=None)
            return None

        options = tuple(selector) if selector is not None else (ShipSelector(name=name),)
        selected = workflow.select_ship(
            self._ctx,
            self._page,
            slot,
            options,
            use_search=self._use_search,
        )
        if selected is None:
            raise RuntimeError(f'未找到满足条件的目标舰船: {[option.name for option in options]}')
        self._emit_fleet_event(
            'ship_selected',
            slot=slot + 1,
            option=options[0] if len(options) == 1 else options,
            selected=selected,
        )
        return selected

    @staticmethod
    def _option_matches_name(current_name: str | None, option: ShipSelector) -> bool:
        """判断当前舰名是否符合一条规则。"""
        return rules.FleetRules._option_matches_name(current_name, option)

    @staticmethod
    def _requires_selection_validation(option: ShipSelector | None) -> bool:
        """判断规则是否需要船池页面复核舰种或等级。"""
        return rules.FleetRules._requires_selection_validation(option)

    @staticmethod
    def _snapshot_satisfies_option(
        snapshot: FleetSnapshot,
        slot: int,
        option: ShipSelector,
    ) -> bool:
        """判断快照中某槽位的舰种和等级是否满足规则。"""
        return rules.FleetRules._snapshot_satisfies_option(snapshot, slot, option)

    def _plan_target_options(
        self,
        selectors: list[FleetSlotRule | None],
        current: Sequence[str | None] = (),
        unavailable: set[tuple[int, ShipSelector]]
        | frozenset[tuple[int, ShipSelector]] = frozenset(),
        locked: dict[int, ShipSelector] | None = None,
    ) -> list[ShipSelector | None] | None:
        """调用规划节点生成全局唯一的目标选项。"""
        return self._planner._plan_target_options(selectors, current, unavailable, locked)

    def _target_names(self, assigned: Sequence[ShipSelector | None]) -> list[str | None]:
        """调用规划节点生成最终目标舰名。"""
        return self._planner._target_names(assigned)

    def _assignment_locations(
        self,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int] | frozenset[int],
    ) -> tuple[set[int], set[int], dict[int, int]]:
        """调用规划节点定位当前成员和目标槽位。"""
        return self._planner._assignment_locations(current, occupied, assigned, verified_slots)

    def _target_order(
        self,
        assigned: Sequence[ShipSelector | None],
        selectors: Sequence[FleetSlotRule | None],
    ) -> list[int]:
        """调用规划节点生成目标处理顺序。"""
        return self._planner._target_order(assigned, selectors)

    def _replacement_slot(
        self,
        current: Sequence[str | None],
        occupied: Sequence[bool],
        option: ShipSelector,
        protected: set[int],
        target_position: int | None,
        attempted: set[tuple[int, ShipSelector, int]],
        target_slot: int,
    ) -> int | None:
        """调用规划节点选择下一次补船位置。"""
        return self._planner._replacement_slot(
            current,
            occupied,
            option,
            protected,
            target_position,
            attempted,
            target_slot,
        )

    def _mark_snapshot_verified_slots(
        self,
        snapshot: FleetSnapshot,
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int],
    ) -> None:
        """调用规划节点标记快照已验证的逻辑槽位。"""
        self._planner._mark_snapshot_verified_slots(snapshot, assigned, verified_slots)

    @staticmethod
    def _deferred_primary_slots(
        snapshot: FleetSnapshot,
        selectors: Sequence[FleetSlotRule | None],
        assigned: Sequence[ShipSelector | None],
    ) -> set[int]:
        """标记身份未知且需要进入主选兜底流程的槽位。"""
        return {
            slot
            for slot, (name, occupied, selector, option) in enumerate(
                zip(snapshot.names, snapshot.occupied, selectors, assigned, strict=True),
            )
            if occupied
            and name is None
            and selector is not None
            and selector.primary is not None
            and option == selector.primary
        }

    def _select_deferred_fallback(
        self,
        target_slot: int,
        selector: FleetSlotRule,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        unavailable: set[tuple[int, ShipSelector]],
    ) -> ShipSelector | None:
        """在原物理槽位按 YAML 顺序选择一个全局不冲突的备选。"""
        blocked_identities = {
            identity
            for slot, name in enumerate(current)
            if slot != target_slot
            and occupied[slot]
            and (identity := ship_name_identity(name)) is not None
        }
        blocked_identities.update(
            identity
            for slot, option in enumerate(assigned)
            if slot != target_slot
            and option is not None
            and (identity := ship_name_identity(option.name)) is not None
        )
        for candidate in selector.candidates:
            identity = ship_name_identity(candidate.name)
            if (
                identity is None
                or identity in blocked_identities
                or (target_slot, candidate) in unavailable
            ):
                continue

            _log.debug(
                "[Fleet] 槽位 {} 身份未知，先用备选 '{}' 释放原舰船",
                target_slot + 1,
                candidate.name,
            )
            previous_name = current[target_slot]
            selection = self._try_select_option(target_slot, candidate)
            if selection.name is None:
                unavailable.add((target_slot, candidate))
                continue
            if not self._option_matches_name(selection.name, candidate):
                raise RuntimeError(
                    f'选船结果 {selection.name!r} 与规则 {candidate.name!r} 不一致',
                )

            current[target_slot] = selection.name
            occupied[target_slot] = True
            _log.info(
                "[Fleet] 换船: 槽位{} '{}' -> '{}'",
                target_slot + 1,
                previous_name or '未知舰船',
                selection.name,
            )
            time.sleep(constants.ACTION_WAIT)
            return candidate
        return None

    def _try_deferred_primary(
        self,
        target_slot: int,
        primary: ShipSelector,
        current: list[str | None],
        verified_slots: set[int],
        locked: dict[int, ShipSelector],
    ) -> bool:
        """尝试主选并同步已确认的槽位状态。"""
        previous_name = current[target_slot]
        selection = self._try_select_option(target_slot, primary)
        if selection.name is None:
            return False
        if not self._option_matches_name(selection.name, primary):
            raise RuntimeError(
                f'选船结果 {selection.name!r} 与规则 {primary.name!r} 不一致',
            )

        current[target_slot] = selection.name
        _log.info(
            "[Fleet] 换船: 槽位{} '{}' -> '{}'",
            target_slot + 1,
            previous_name or '未知舰船',
            selection.name,
        )
        locked[target_slot] = primary
        verified_slots.discard(target_slot)
        if self._requires_selection_validation(primary):
            verified_slots.add(target_slot)
        time.sleep(constants.ACTION_WAIT)
        return True

    def _resolve_deferred_primaries(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int],
        initial_snapshot: FleetSnapshot | None,
    ) -> None:
        """处理未知主选：有备选时释放回查，无备选时单次搜索。"""
        for target_slot in sorted(deferred_primary_slots):
            deferred_primary_slots.discard(target_slot)
            selector = selectors[target_slot]
            if (
                selector is None
                or selector.primary is None
                or assigned[target_slot] != selector.primary
                or not occupied[target_slot]
                or current[target_slot] is not None
            ):
                continue

            primary = selector.primary
            fallback: ShipSelector | None = None
            if selector.candidates:
                fallback = self._select_deferred_fallback(
                    target_slot,
                    selector,
                    current,
                    occupied,
                    assigned,
                    unavailable,
                )
                if fallback is None:
                    _log.debug(
                        '[Fleet] 槽位 {} 没有可用备选，保留原换船流程',
                        target_slot + 1,
                    )
                    continue
                _log.debug(
                    "[Fleet] 槽位 {} 已释放，重新尝试主选 '{}'",
                    target_slot + 1,
                    primary.name,
                )
            else:
                _log.debug(
                    "[Fleet] 槽位 {} 身份未知且没有备选，最后搜索一次主选 '{}'",
                    target_slot + 1,
                    primary.name,
                )

            if self._try_deferred_primary(
                target_slot,
                primary,
                current,
                verified_slots,
                locked,
            ):
                continue

            if fallback is None:
                raise _UnresolvedPrimaryError(
                    f"槽位 {target_slot + 1} 的主选 '{primary.name}' 选择失败："
                    '准备页连续 OCR 后仍无法确认，船池搜索和 OCR 也未找到；'
                    '可能是主选 OCR 识别失败，或账号不存在该舰船，已停止本次换船',
                )

            unavailable.add((target_slot, primary))
            locked[target_slot] = fallback
            previous = list(assigned)
            replanned = self._plan_target_options(
                selectors,
                current,
                unavailable,
                locked,
            )
            if replanned is None:
                raise RuntimeError(
                    f'目标槽位 {target_slot} 的主选和已选备选无法组成有效舰队',
                )
            assigned[:] = replanned
            for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
                if old != new:
                    verified_slots.discard(slot)
            if self._requires_selection_validation(fallback):
                verified_slots.add(target_slot)
            if initial_snapshot is not None:
                self._mark_snapshot_verified_slots(
                    initial_snapshot,
                    assigned,
                    verified_slots,
                )
            _log.info(
                '[Fleet] YAML目标编队调整: {} -> {}',
                self._target_names(previous),
                self._target_names(replanned),
            )

    def _align_member_set(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int] | None = None,
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """只处理成员集合；不拖拽最终顺序，也不删除多余舰船。"""
        if deferred_primary_slots:
            self._resolve_deferred_primaries(
                current,
                occupied,
                assigned,
                selectors,
                verified_slots,
                unavailable,
                locked,
                deferred_primary_slots,
                initial_snapshot,
            )

        attempted: set[tuple[int, ShipSelector, int]] = set()
        for _ in range(48):
            protected, satisfied, target_positions = self._assignment_locations(
                current,
                occupied,
                assigned,
                verified_slots,
            )
            missing = [
                slot for slot in self._target_order(assigned, selectors) if slot not in satisfied
            ]
            if not missing:
                return

            target_slot = missing[0]
            option = assigned[target_slot]
            assert option is not None
            ship_slot = self._replacement_slot(
                current,
                occupied,
                option,
                protected,
                target_positions.get(target_slot),
                attempted,
                target_slot,
            )
            if ship_slot is None:
                _log.debug(
                    "[Fleet] 目标槽位 {} 的规则 '{}' 不可用，重新规划备选",
                    target_slot + 1,
                    option.name,
                )
                unavailable.add((target_slot, option))
                locked.pop(target_slot, None)
                verified_slots.discard(target_slot)
                previous = list(assigned)
                replanned = self._plan_target_options(
                    selectors,
                    current,
                    unavailable,
                    locked,
                )
                if replanned is None:
                    raise RuntimeError(
                        f'目标槽位 {target_slot} 的主选和备选均不可用',
                    )
                assigned[:] = replanned
                for slot, (old, new) in enumerate(
                    zip(previous, replanned, strict=True),
                ):
                    if old != new:
                        verified_slots.discard(slot)
                # 重规划后新分配的备选若已在队内且满足约束，直接用首次快照
                # 标记为已验证，避免已就位备选不在船池时反复进选船页重选。
                if initial_snapshot is not None:
                    self._mark_snapshot_verified_slots(
                        initial_snapshot,
                        assigned,
                        verified_slots,
                    )
                _log.info(
                    '[Fleet] YAML目标编队调整: {} -> {}',
                    self._target_names(previous),
                    self._target_names(replanned),
                )
                continue

            _log.debug(
                "[Fleet] 更换物理槽位 {} <- '{}' (逻辑槽位 {}, 原: '{}')",
                ship_slot + 1,
                option.name,
                target_slot + 1,
                current[ship_slot],
            )
            previous_name = current[ship_slot]
            selection = self._try_select_option(
                ship_slot,
                option,
            )
            attempted.add((target_slot, option, ship_slot))
            if selection.name is None:
                continue
            if not self._option_matches_name(selection.name, option):
                raise RuntimeError(
                    f'选船结果 {selection.name!r} 与规则 {option.name!r} 不一致',
                )

            current[ship_slot] = selection.name
            occupied[ship_slot] = True
            _log.info(
                "[Fleet] 换船: 槽位{} '{}' -> '{}'",
                ship_slot + 1,
                previous_name or '空槽',
                selection.name,
            )
            locked[target_slot] = option
            verified_slots.discard(target_slot)
            if self._requires_selection_validation(option):
                verified_slots.add(target_slot)
            time.sleep(constants.ACTION_WAIT)

        raise RuntimeError('成员集合调整次数超过安全上限')

    def _remove_extra_members(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: Sequence[ShipSelector | None],
        verified_slots: set[int],
    ) -> None:
        """目标成员齐全后，从后往前删除所有多余或未知成员。"""
        protected, _, _ = self._assignment_locations(
            current,
            occupied,
            assigned,
            verified_slots,
        )
        for slot in range(5, -1, -1):
            if slot in protected or not occupied[slot]:
                continue
            previous_name = current[slot]
            self._change_single_ship(slot, None, slot_occupied=True)
            _log.info(
                "[Fleet] 换船: 槽位{} '{}' -> 空槽",
                slot + 1,
                previous_name or '未知舰船',
            )
            # 游戏会将右侧舰船整体左移，直接同步已确认的成员位置。
            current.pop(slot)
            current.append(None)
            occupied.pop(slot)
            occupied.append(False)
            time.sleep(constants.ACTION_WAIT)

    # 首次调整时完成成员复用、缺员补充和多余成员移除。
    def _full_align(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        deferred_primary_slots: set[int] | None = None,
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """首次将当前舰队调整为目标成员集合。"""
        self._align_member_set(
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
            unavailable,
            locked,
            deferred_primary_slots,
            initial_snapshot,
        )
        self._remove_extra_members(current, occupied, assigned, verified_slots)

    # OCR 验证失败后，只修正成员集合，不在此阶段拖拽排序。
    def _local_fix(
        self,
        current: list[str | None],
        occupied: list[bool],
        assigned: list[ShipSelector | None],
        selectors: list[FleetSlotRule | None],
        verified_slots: set[int],
        unavailable: set[tuple[int, ShipSelector]],
        locked: dict[int, ShipSelector],
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """重试时重新补齐成员，再清理多余成员。"""
        self._align_member_set(
            current,
            occupied,
            assigned,
            selectors,
            verified_slots,
            unavailable,
            locked,
            initial_snapshot=initial_snapshot,
        )
        self._remove_extra_members(current, occupied, assigned, verified_slots)

    # 从左到右拖拽舰船，使当前舰队顺序与目标槽位一致。
    def _reorder(
        self,
        current: list[str | None],
        desired: list[str | None],
    ) -> None:
        """通过拖拽调整舰船顺序，并同步更新 current。"""
        for i in range(6):
            target = desired[i]
            if target is None:
                break
            target_identity = ship_name_identity(target)
            if ship_name_identity(current[i]) == target_identity:
                continue
            try:
                src = next(
                    idx
                    for idx, current_name in enumerate(current)
                    if ship_name_identity(current_name) == target_identity
                )
            # 当前舰队中找不到目标舰船时，保留现场交给最终验证处理。
            except StopIteration:
                _log.warning(
                    "[Fleet] 位置对齐: '{}' 不在当前舰队中, 跳过",
                    target,
                )
                continue
            _log.debug(
                "[Fleet] 位置对齐: 槽位 {} <- '{}' (从槽位 {})",
                i + 1,
                target,
                src + 1,
            )
            self._circular_move(src, i, current)
            _log.info(
                "[Fleet] 调整位置: '{}' 槽位{} -> 槽位{}",
                target,
                src + 1,
                i + 1,
            )

    # 将一艘舰船从源槽位拖到目标槽位，并模拟游戏中的循环位移。
    def _circular_move(
        self,
        src: int,
        dst: int,
        current: list[str | None],
    ) -> None:
        """执行一次拖拽，并更新内存中的舰队顺序。"""
        # 源槽位和目标槽位相同时，不需要执行拖拽。
        if src == dst:
            return
        # sx、sy 是源槽位坐标，dx、dy 是目标槽位坐标。
        sx, sy = CLICK_SHIP_SLOT[src]
        dx, dy = CLICK_SHIP_SLOT[dst]
        self._emit_fleet_event(
            'ship_moved',
            source=src + 1,
            destination=dst + 1,
        )
        self._ctrl.swipe(sx, sy, dx, dy, duration=0.5)

        # ship 是从源槽位取出的舰名，用于同步游戏中的循环位移。
        ship = current.pop(src)
        current.insert(dst, ship)
        time.sleep(constants.REORDER_WAIT)
