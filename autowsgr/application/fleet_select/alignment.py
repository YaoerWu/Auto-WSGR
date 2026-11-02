"""模块功能：把当前编队调整成目标成员集合，并按目标顺序排好。

上层调用：
- fleet_select.battle_preparation.normal：普通出征、活动、演习的换船主流程。
- fleet_select.battle_preparation.decisive：决战换船主流程。

下层依赖：
- fleet_select.planning：目标分配、槽位定位与处理顺序。
- fleet_select.rules：舰名与规则比对。
- fleet_select.ship_pool：单槽换船与清空。
- controller.sortie.battle_preparation.ship_recognition.page：点开槽位、拖拽舰船。
- application.errors：换船失败时抛出具体操作错误。

边界：只执行已经规划好的目标，不读图、不判断阵容是否合格、不决定换哪个舰队。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.page import (
    FleetSlotPage,
)
from autowsgr.application.errors import ActionFailedError
from autowsgr.application.fleet_select import planning, rules
from autowsgr.application.fleet_select.constants import (
    ACTION_WAIT,
    MAX_ALIGN_STEPS,
    REORDER_WAIT,
)
from autowsgr.application.fleet_select.models import FLEET_SLOT_COUNT
from autowsgr.application.fleet_select.names import ship_name_identity
from autowsgr.application.fleet_select.ship_pool import remove_ship, select_ship
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.fleet_select.models import (
        FleetSlotRule,
        FleetSnapshot,
        ShipSelector,
    )
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.alignment')


# ── 状态定位 ────────────────────────────────────────────────────────────────


def find_deferred_primary_slots(
    snapshot: FleetSnapshot,
    selectors: Sequence[FleetSlotRule | None],
    assigned: Sequence[ShipSelector | None],
) -> set[int]:
    """定位身份未知、需要先进主选兜底流程的逻辑槽位。

    Args:
        snapshot: 首次截图得到的舰队快照。
        selectors: 逐槽原始规则。
        assigned: 逐槽精确规则。

    Returns:
        已占用但舰名未识别、且规划上仍是主选的零基逻辑槽位集合。
    """
    return {
        slot
        for slot, (name, is_occupied, selector, option) in enumerate(
            zip(snapshot.names, snapshot.occupied, selectors, assigned, strict=True),
        )
        if is_occupied
        and name is None
        and selector is not None
        and selector.primary is not None
        and option == selector.primary
    }


# ── 换船执行 ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class FleetAligner:
    """一次换船过程中的可变编队状态与动作。"""

    ctx: ContextHandle
    selectors: Sequence[FleetSlotRule | None]
    use_search: bool = True
    notify: Callable[[str, dict[str, object]], None] | None = None

    current: list[str | None] = field(default_factory=list)
    occupied: list[bool] = field(default_factory=list)
    assigned: list[ShipSelector | None] = field(default_factory=list)
    verified_slots: set[int] = field(default_factory=set)
    unavailable: set[tuple[int, ShipSelector]] = field(default_factory=set)
    locked: dict[int, ShipSelector] = field(default_factory=dict)

    def align_fleet(
        self,
        *,
        deferred_primary_slots: set[int] | None = None,
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """首次把当前舰队调整成目标成员集合，再清掉多余成员。

        Args:
            deferred_primary_slots: 需要先进主选兜底流程的零基逻辑槽位。
            initial_snapshot: 首次截图快照，用来标记已就位槽位免于二次确认。
        """
        self._align_member_set(
            deferred_primary_slots=deferred_primary_slots,
            initial_snapshot=initial_snapshot,
        )
        self._remove_extra_members()

    def fix_fleet(self, *, initial_snapshot: FleetSnapshot | None = None) -> None:
        """校验失败后只补齐成员集合，不做位置对齐。

        Args:
            initial_snapshot: 首次截图快照，用来标记已就位槽位免于二次确认。
        """
        self._align_member_set(initial_snapshot=initial_snapshot)
        self._remove_extra_members()

    def reorder_fleet(self) -> None:
        """按目标顺序从左到右拖拽舰船。"""
        desired = planning.target_names(self.assigned)
        for target_slot in range(FLEET_SLOT_COUNT):
            target = desired[target_slot]
            if target is None:
                break
            identity = ship_name_identity(target)
            if ship_name_identity(self.current[target_slot]) == identity:
                continue

            source = next(
                (
                    slot
                    for slot, name in enumerate(self.current)
                    if ship_name_identity(name) == identity
                ),
                None,
            )
            if source is None:
                _log.warning("[换船] 位置对齐: '{}' 不在当前舰队中, 跳过", target)
                continue
            _log.debug(
                "[换船] 位置对齐: 槽位 {} <- '{}' (从槽位 {})", target_slot + 1, target, source + 1
            )
            self._circular_move(source, target_slot)
            _log.info("[换船] 调整位置: '{}' 槽位{} -> 槽位{}", target, source + 1, target_slot + 1)

    # ── 成员集合 ────────────────────────────────────────────────────────────

    def _align_member_set(
        self,
        *,
        deferred_primary_slots: set[int] | None = None,
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """只处理成员集合，不拖拽顺序，也不删除多余舰船。"""
        if deferred_primary_slots:
            self._resolve_deferred_primaries(deferred_primary_slots, initial_snapshot)

        attempted: set[tuple[int, ShipSelector, int]] = set()
        for _ in range(MAX_ALIGN_STEPS):
            protected, satisfied, target_positions = planning.assignment_locations(
                self.current,
                self.occupied,
                self.assigned,
                self.verified_slots,
            )
            missing = [
                slot
                for slot in planning.target_order(self.assigned, self.selectors)
                if slot not in satisfied
            ]
            if not missing:
                return

            target_slot = missing[0]
            option = self.assigned[target_slot]
            if option is None:
                continue
            ship_slot = planning.replacement_slot(
                self.current,
                self.occupied,
                option,
                protected,
                target_positions.get(target_slot),
                attempted,
                target_slot,
            )
            if ship_slot is None:
                _log.debug(
                    "[换船] 目标槽位 {} 的规则 '{}' 不可用，重新规划备选",
                    target_slot + 1,
                    option.name,
                )
                self._replan(target_slot, option, initial_snapshot)
                continue

            _log.debug(
                "[换船] 更换物理槽位 {} <- '{}' (逻辑槽位 {}, 原: '{}')",
                ship_slot + 1,
                option.name,
                target_slot + 1,
                self.current[ship_slot],
            )
            previous_name = self.current[ship_slot]
            selected = self._select_option(ship_slot, option)
            attempted.add((target_slot, option, ship_slot))
            if selected is None:
                continue
            if not rules.option_matches_name(selected, option):
                raise ActionFailedError(
                    '选择舰船',
                    f'选船结果 {selected!r} 与规则 {option.name!r} 不一致',
                )

            self.current[ship_slot] = selected
            self.occupied[ship_slot] = True
            self._emit('ship_selected', {'slot': ship_slot + 1, 'selected': selected})
            _log.info(
                "[换船] 换船: 槽位{} '{}' -> '{}'",
                ship_slot + 1,
                previous_name or '空槽',
                selected,
            )
            self.locked[target_slot] = option
            self.verified_slots.discard(target_slot)
            if rules.requires_selection_validation(option):
                self.verified_slots.add(target_slot)
            time.sleep(ACTION_WAIT)

        raise ActionFailedError('调整舰队', '成员集合调整次数超过安全上限')

    def _replan(
        self,
        target_slot: int,
        option: ShipSelector,
        initial_snapshot: FleetSnapshot | None,
    ) -> None:
        """把一条不可用的规则记为不可用，并重新做一次全局分配。"""
        self.unavailable.add((target_slot, option))
        self.locked.pop(target_slot, None)
        self.verified_slots.discard(target_slot)

        previous = list(self.assigned)
        replanned = planning.plan_target_options(
            self.selectors,
            self.current,
            self.unavailable,
            self.locked,
        )
        if replanned is None:
            raise ActionFailedError(
                '调整舰队',
                f'目标槽位 {target_slot + 1} 的主选和备选均不可用',
            )

        self.assigned[:] = replanned
        for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
            if old != new:
                self.verified_slots.discard(slot)
        self._mark_snapshot_verified_slots(initial_snapshot)
        _log.info(
            '[换船] 目标编队调整: {} -> {}',
            planning.target_names(previous),
            planning.target_names(replanned),
        )

    def _remove_extra_members(self) -> None:
        """目标成员齐全后，从后往前删除所有多余或未知成员。"""
        protected, _, _ = planning.assignment_locations(
            self.current,
            self.occupied,
            self.assigned,
            self.verified_slots,
        )
        for slot in range(FLEET_SLOT_COUNT - 1, -1, -1):
            if slot in protected or not self.occupied[slot]:
                continue
            previous_name = self.current[slot]
            remove_ship(self.ctx, slot=slot + 1)
            self._emit('ship_removed', {'slot': slot + 1})
            _log.info("[换船] 换船: 槽位{} '{}' -> 空槽", slot + 1, previous_name or '未知舰船')

            # 游戏会把右侧舰船整体左移，内存里同步做一次压缩。
            self.current.pop(slot)
            self.current.append(None)
            self.occupied.pop(slot)
            self.occupied.append(False)
            time.sleep(ACTION_WAIT)

    # ── 主选兜底 ────────────────────────────────────────────────────────────

    def _resolve_deferred_primaries(
        self,
        deferred_primary_slots: set[int],
        initial_snapshot: FleetSnapshot | None,
    ) -> None:
        """处理身份未知的主选槽位：有备选时先释放再回查，没有备选时最后搜一次。"""
        for target_slot in sorted(deferred_primary_slots):
            deferred_primary_slots.discard(target_slot)
            selector = self.selectors[target_slot]
            if (
                selector is None
                or selector.primary is None
                or self.assigned[target_slot] != selector.primary
                or not self.occupied[target_slot]
                or self.current[target_slot] is not None
            ):
                continue

            primary = selector.primary
            fallback: ShipSelector | None = None
            if selector.candidates:
                fallback = self._select_deferred_fallback(target_slot, selector)
                if fallback is None:
                    _log.debug('[换船] 槽位 {} 没有可用备选，保留原换船流程', target_slot + 1)
                    continue
                _log.debug(
                    "[换船] 槽位 {} 已释放，重新尝试主选 '{}'", target_slot + 1, primary.name
                )
            else:
                _log.debug(
                    "[换船] 槽位 {} 身份未知且没有备选，最后搜索一次主选 '{}'",
                    target_slot + 1,
                    primary.name,
                )

            if self._try_deferred_primary(target_slot, primary):
                continue
            if fallback is None:
                raise ActionFailedError(
                    '选择舰船',
                    f"槽位 {target_slot + 1} 的主选 '{primary.name}' 选择失败："
                    '准备页连续 OCR 后仍无法确认，船池搜索和 OCR 也未找到；'
                    '可能是主选 OCR 识别失败，或账号不存在该舰船，已停止本次换船',
                )

            self.unavailable.add((target_slot, primary))
            self.locked[target_slot] = fallback
            previous = list(self.assigned)
            replanned = planning.plan_target_options(
                self.selectors,
                self.current,
                self.unavailable,
                self.locked,
            )
            if replanned is None:
                raise ActionFailedError(
                    '调整舰队',
                    f'目标槽位 {target_slot} 的主选和已选备选无法组成有效舰队',
                )
            self.assigned[:] = replanned
            for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
                if old != new:
                    self.verified_slots.discard(slot)
            if rules.requires_selection_validation(fallback):
                self.verified_slots.add(target_slot)
            self._mark_snapshot_verified_slots(initial_snapshot)
            _log.info(
                '[换船] 目标编队调整: {} -> {}',
                planning.target_names(previous),
                planning.target_names(replanned),
            )

    def _select_deferred_fallback(
        self,
        target_slot: int,
        selector: FleetSlotRule,
    ) -> ShipSelector | None:
        """在原物理槽位按规则顺序挑一个全局不冲突的备选先顶上。"""
        blocked = {
            identity
            for slot, name in enumerate(self.current)
            if slot != target_slot
            and self.occupied[slot]
            and (identity := ship_name_identity(name)) is not None
        }
        blocked.update(
            identity
            for slot, option in enumerate(self.assigned)
            if slot != target_slot
            and option is not None
            and (identity := ship_name_identity(option.name)) is not None
        )

        for candidate in selector.candidates:
            identity = ship_name_identity(candidate.name)
            if (
                identity is None
                or identity in blocked
                or (target_slot, candidate) in self.unavailable
            ):
                continue

            _log.debug(
                "[换船] 槽位 {} 身份未知，先用备选 '{}' 释放原舰船",
                target_slot + 1,
                candidate.name,
            )
            previous_name = self.current[target_slot]
            selected = self._select_option(target_slot, candidate)
            if selected is None:
                self.unavailable.add((target_slot, candidate))
                continue
            if not rules.option_matches_name(selected, candidate):
                raise ActionFailedError(
                    '选择舰船',
                    f'选船结果 {selected!r} 与规则 {candidate.name!r} 不一致',
                )

            self.current[target_slot] = selected
            self.occupied[target_slot] = True
            _log.info(
                "[换船] 换船: 槽位{} '{}' -> '{}'",
                target_slot + 1,
                previous_name or '未知舰船',
                selected,
            )
            time.sleep(ACTION_WAIT)
            return candidate
        return None

    def _try_deferred_primary(self, target_slot: int, primary: ShipSelector) -> bool:
        """尝试一次主选，成功就锁定该槽位并记录校验状态。"""
        previous_name = self.current[target_slot]
        selected = self._select_option(target_slot, primary)
        if selected is None:
            return False
        if not rules.option_matches_name(selected, primary):
            raise ActionFailedError(
                '选择舰船',
                f'选船结果 {selected!r} 与规则 {primary.name!r} 不一致',
            )

        self.current[target_slot] = selected
        _log.info(
            "[换船] 换船: 槽位{} '{}' -> '{}'",
            target_slot + 1,
            previous_name or '未知舰船',
            selected,
        )
        self.locked[target_slot] = primary
        self.verified_slots.discard(target_slot)
        if rules.requires_selection_validation(primary):
            self.verified_slots.add(target_slot)
        time.sleep(ACTION_WAIT)
        return True

    # ── 通用动作 ────────────────────────────────────────────────────────────

    def _select_option(self, slot: int, option: ShipSelector) -> str | None:
        """在指定零基物理槽位尝试一条选船规则。"""
        return select_ship(
            self.ctx,
            slot=slot + 1,
            selectors=(option,),
            use_search=self.use_search,
        )

    def _mark_snapshot_verified_slots(self, snapshot: FleetSnapshot | None) -> None:
        """用首次快照标记已就位槽位，避免已选好的舰船再进一次船池。"""
        if snapshot is None:
            return
        planning.mark_snapshot_verified_slots(snapshot, self.assigned, self.verified_slots)

    def _circular_move(self, source: int, target: int) -> None:
        """把一艘舰船从源槽位拖到目标槽位，并同步内存顺序。"""
        if source == target:
            return
        self._emit('ship_moved', {'source': source + 1, 'destination': target + 1})
        FleetSlotPage(self.ctx).drag_slot(source + 1, target + 1)
        self.current.insert(target, self.current.pop(source))
        time.sleep(REORDER_WAIT)

    def _emit(self, event: str, data: dict[str, object]) -> None:
        """向上层报告一个已经完成的编队动作。"""
        if self.notify is not None:
            self.notify(event, data)


__all__ = ['FleetAligner', 'find_deferred_primary_slots']
