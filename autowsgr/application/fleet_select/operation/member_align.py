"""模块功能：把当前编队调整成目标成员集合，并按目标顺序排好。

上层调用：
- fleet_select.models.normal：普通出征、活动、演习的换船主流程。
- fleet_select.models.decisive：决战换船主流程。

下层依赖：
- fleet_select.rules.planner：下一步动作、目标分配与槽位定位。
- fleet_select.rules.constraints：是否需要船池二次校验。
- fleet_select.operation.fleet_snapshot：位置对齐后重新识别六槽顺序。
- fleet_select.operation.ship_select：单槽换船与清空。
- controller.sortie.battle_preparation.ship_recognition.page：拖拽舰船。
- fleet_select.models.progress：向上层播报编队动作。

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
from autowsgr.application.fleet_select.constants import (
    ACTION_WAIT,
    MAX_ALIGN_STEPS,
    MAX_REORDER_STEPS,
    REORDER_WAIT,
)
from autowsgr.application.fleet_select.models.progress import report_progress
from autowsgr.application.fleet_select.operation.fleet_snapshot import read_fleet_snapshot
from autowsgr.application.fleet_select.operation.ship_select import remove_ship, select_ship
from autowsgr.application.fleet_select.rules import constraints, planner
from autowsgr.application.fleet_select.rules.shipnames import get_ship_name_identity
from autowsgr.application.fleet_select.types import FLEET_SLOT_COUNT
from autowsgr.common.system.logger import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autowsgr.application.fleet_select.rules.planner import MemberStep
    from autowsgr.application.fleet_select.types import (
        FleetSlotRule,
        FleetSnapshot,
        ShipSelector,
    )
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('fleet_select.operation.member_align')


class UnresolvedPrimaryError(RuntimeError):
    """连续 OCR 后仍无法确认唯一主选时终止本次换船。"""


# ── 对齐状态与换船执行 ──────────────────────────────────────────────────────


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
    attempted: set[tuple[int, ShipSelector, int]] = field(default_factory=set)

    # ── 成员集合对齐 ────────────────────────────────────────────────────────

    def execute_member_plan(
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
        self._execute_member_steps(
            deferred_primary_slots=deferred_primary_slots,
            initial_snapshot=initial_snapshot,
        )
        self._remove_extra_members()

    def execute_member_fix(self, *, initial_snapshot: FleetSnapshot | None = None) -> None:
        """校验失败后只补齐成员集合，不做位置对齐。

        Args:
            initial_snapshot: 首次截图快照，用来标记已就位槽位免于二次确认。
        """
        self._execute_member_steps(initial_snapshot=initial_snapshot)
        self._remove_extra_members()

    def execute_member_reorder(self) -> None:
        """按目标顺序从左到右拖拽舰船，每拖一步都以重新识别到的顺序为准。

        单次拖拽的落点偶尔会偏一格。如果照内存里的顺序连着拖，一次偏移就会
        让后面每一步都落在错误的槽位上，所以每拖一步都重新识别一次页面顺序。
        """
        desired = planner.get_target_names(self.assigned)
        for _ in range(MAX_REORDER_STEPS):
            self._refresh_page_order()
            target_slot = self._find_misplaced_slot(desired)
            if target_slot is None:
                return

            target = desired[target_slot]
            identity = get_ship_name_identity(target)
            source = next(
                (
                    slot
                    for slot, name in enumerate(self.current)
                    if get_ship_name_identity(name) == identity
                ),
                None,
            )
            if source is None:
                # 名字不在当前舰队里属于预期的跳过，不是异常，记 DEBUG 即可。
                _log.debug('[FLEET] 位置对齐 → 跳过：name={!r}, 不在当前舰队中', target)
                return
            self._move_member(source, target_slot)
            _log.debug(
                '[FLEET] 位置对齐 → 移动：name={!r}, source={}, target={}',
                target,
                source + 1,
                target_slot + 1,
            )

    def _refresh_page_order(self) -> None:
        """用当前页面的识别结果刷新六槽舰名，识别不到的槽位保留原值。"""
        snapshot = read_fleet_snapshot(self.ctx, include_details=False)
        for slot, (name, occupied) in enumerate(
            zip(snapshot.names, snapshot.occupied, strict=True)
        ):
            if occupied and name is not None:
                self.current[slot] = name

    def _find_misplaced_slot(self, desired: Sequence[str | None]) -> int | None:
        """返回第一个顺序不符的槽位，全部就位时为空。

        Args:
            desired: 与槽位对齐的目标舰名，空槽为 None。

        Returns:
            零基槽位序号；已经对齐或没有可拖拽的舰船时为空。
        """
        identities = [get_ship_name_identity(name) for name in self.current]
        for slot, name in enumerate(desired):
            if name is None:
                return None
            identity = get_ship_name_identity(name)
            if identity is None or identity not in identities:
                continue
            if identities[slot] != identity:
                return slot
        return None

    def _execute_member_steps(
        self,
        *,
        deferred_primary_slots: set[int] | None = None,
        initial_snapshot: FleetSnapshot | None = None,
    ) -> None:
        """只处理成员集合，不拖拽顺序，也不删除多余舰船。

        Args:
            deferred_primary_slots: 需要最后回查身份的主选槽位。
            initial_snapshot: 进入本次对齐前的快照，用于判断槽位是否需要复核。
        """
        if deferred_primary_slots:
            self._resolve_deferred_primaries(deferred_primary_slots, initial_snapshot)

        for _ in range(MAX_ALIGN_STEPS):
            step = planner.plan_member_step(self._build_state())
            if step.kind == 'done':
                return
            if step.kind == 'skip':
                continue
            if step.kind == 'replan':
                _log.debug(
                    '[FLEET] 换船 → 重新规划：slot={}, rule={!r}, 规则不可用',
                    step.target_slot + 1,
                    step.option.name if step.option is not None else '',
                )
                self._replan(step.target_slot, step.option, initial_snapshot)
                continue
            self._execute_select(step)

    def _execute_select(self, step: MemberStep) -> None:
        """在一个物理槽位点选目标船，并记录锁定与校验状态。

        Args:
            step: 规划器给出的选船步骤，含目标槽位、物理槽位与选船规则。
        """
        target_slot = step.target_slot
        ship_slot = step.ship_slot
        option = step.option
        if option is None:
            return

        previous_name = self.current[ship_slot]
        selected = self._select_option(ship_slot, option)
        self.attempted.add((target_slot, option, ship_slot))
        if selected is None:
            return

        self.current[ship_slot] = selected
        self.occupied[ship_slot] = True
        report_progress(self.notify, 'ship_selected', {'slot': ship_slot + 1, 'selected': selected})
        _log.debug(
            '[FLEET] 换船 → 选中：slot={}, selected={!r}, previous={!r}',
            ship_slot + 1,
            selected,
            previous_name,
        )
        self.locked[target_slot] = option
        self.verified_slots.discard(target_slot)
        if constraints.should_validate_selection(option):
            self.verified_slots.add(target_slot)
        time.sleep(ACTION_WAIT)

    def _replan(
        self,
        target_slot: int,
        option: ShipSelector | None,
        initial_snapshot: FleetSnapshot | None,
    ) -> None:
        """把一条不可用的规则记为不可用，并重新做一次全局分配。

        Args:
            target_slot: 规则不可用的目标槽位。
            option: 被判定不可用的选船规则；没有具体规则时为空。
            initial_snapshot: 进入本次对齐前的快照，用于判断槽位是否需要复核。

        Raises:
            UnresolvedPrimaryError: 重新分配后该槽位没有任何可用规则。
        """
        if option is not None:
            self.unavailable.add((target_slot, option))
        self.locked.pop(target_slot, None)
        self.verified_slots.discard(target_slot)

        previous = list(self.assigned)
        replanned = planner.plan_target_options(
            self.selectors,
            self.current,
            self.unavailable,
            self.locked,
        )
        if replanned is None:
            raise UnresolvedPrimaryError(f'目标槽位 {target_slot + 1} 的主选和备选均不可用')

        self.assigned[:] = replanned
        for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
            if old != new:
                self.verified_slots.discard(slot)
        self._mark_snapshot_verified_slots(initial_snapshot)
        _log.debug(
            '[FLEET] 编队 → 重新分配：previous={}, target={}',
            planner.get_target_names(previous),
            planner.get_target_names(replanned),
        )

    def _remove_extra_members(self) -> None:
        """目标成员齐全后，从后往前删除所有多余或未知成员。"""
        protected, _, _ = planner.get_assignment_locations(
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
            report_progress(self.notify, 'ship_removed', {'slot': slot + 1})
            _log.debug(
                '[FLEET] 换船 → 清空：slot={}, previous={!r}',
                slot + 1,
                previous_name,
            )

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
        """处理身份未知的主选槽位：有备选时先释放再回查，没有备选时最后搜一次。

        Args:
            deferred_primary_slots: 需要最后回查身份的主选槽位。
            initial_snapshot: 进入本次对齐前的快照，用于判断槽位是否需要复核。

        Raises:
            UnresolvedPrimaryError: 主选没有备选，且重试后仍无法确认它的身份。
            ActionFailedError: 换上备选后无法再组成有效舰队。
        """
        for target_slot in sorted(deferred_primary_slots):
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
                    _log.debug(
                        '[FLEET] 主选兜底 → 跳过备选：slot={}, 没有可用备选',
                        target_slot + 1,
                    )
                    continue
                _log.debug(
                    '[FLEET] 主选兜底 → 重试主选：slot={}, primary={!r}',
                    target_slot + 1,
                    primary.name,
                )
            else:
                _log.debug(
                    '[FLEET] 主选兜底 → 兜底搜索：slot={}, primary={!r}, 身份未知且没有备选',
                    target_slot + 1,
                    primary.name,
                )

            if self._try_deferred_primary(target_slot, primary):
                continue
            if fallback is None:
                raise UnresolvedPrimaryError(
                    f"槽位 {target_slot + 1} 的主选 '{primary.name}' 选择失败："
                    '准备页连续 OCR 后仍无法确认，船池搜索和 OCR 也未找到；'
                    '可能是主选 OCR 识别失败，或账号不存在该舰船，已停止本次换船',
                )

            self.unavailable.add((target_slot, primary))
            self.locked[target_slot] = fallback
            previous = list(self.assigned)
            replanned = planner.plan_target_options(
                self.selectors,
                self.current,
                self.unavailable,
                self.locked,
            )
            if replanned is None:
                raise ActionFailedError(
                    '调整舰队',
                    f'目标槽位 {target_slot + 1} 的主选和已选备选无法组成有效舰队',
                )
            self.assigned[:] = replanned
            for slot, (old, new) in enumerate(zip(previous, replanned, strict=True)):
                if old != new:
                    self.verified_slots.discard(slot)
            if constraints.should_validate_selection(fallback):
                self.verified_slots.add(target_slot)
            self._mark_snapshot_verified_slots(initial_snapshot)
            _log.debug(
                '[FLEET] 编队 → 重新分配：previous={}, target={}',
                planner.get_target_names(previous),
                planner.get_target_names(replanned),
            )

    def _select_deferred_fallback(
        self,
        target_slot: int,
        selector: FleetSlotRule,
    ) -> ShipSelector | None:
        """在原物理槽位按规则顺序挑一个全局不冲突的备选先顶上。

        Args:
            target_slot: 主选身份未知的目标槽位。
            selector: 该槽位的主选与备选规则。

        Returns:
            已经选上的备选规则；没有可用备选时为空。
        """
        while True:
            candidate = planner.plan_deferred_fallback(self._build_state(), target_slot, selector)
            if candidate is None:
                return None

            _log.debug(
                '[FLEET] 主选兜底 → 释放槽位：slot={}, candidate={!r}, 身份未知',
                target_slot + 1,
                candidate.name,
            )
            previous_name = self.current[target_slot]
            selected = self._select_option(target_slot, candidate)
            if selected is None:
                self.unavailable.add((target_slot, candidate))
                continue

            self.current[target_slot] = selected
            self.occupied[target_slot] = True
            _log.debug(
                '[FLEET] 换船 → 选中：slot={}, selected={!r}, previous={!r}',
                target_slot + 1,
                selected,
                previous_name,
            )
            time.sleep(ACTION_WAIT)
            return candidate

    def _try_deferred_primary(self, target_slot: int, primary: ShipSelector) -> bool:
        """尝试一次主选，成功就锁定该槽位并记录校验状态。

        Args:
            target_slot: 主选身份未知的目标槽位。
            primary: 该槽位的主选规则。

        Returns:
            主选已选上时为真；选不上时为假，由调用方决定兜底还是放弃。
        """
        previous_name = self.current[target_slot]
        selected = self._select_option(target_slot, primary)
        if selected is None:
            return False

        self.current[target_slot] = selected
        _log.debug(
            '[FLEET] 换船 → 选中：slot={}, selected={!r}, previous={!r}',
            target_slot + 1,
            selected,
            previous_name,
        )
        self.locked[target_slot] = primary
        self.verified_slots.discard(target_slot)
        if constraints.should_validate_selection(primary):
            self.verified_slots.add(target_slot)
        time.sleep(ACTION_WAIT)
        return True

    # ── 槽位动作 ────────────────────────────────────────────────────────────

    def _select_option(self, slot: int, option: ShipSelector) -> str | None:
        """在指定零基物理槽位尝试一条选船规则。

        Args:
            slot: 零基物理槽位序号。
            option: 要尝试的选船规则。

        Returns:
            选上的舰名；该规则不可用或选船失败时为空。
        """
        return select_ship(
            self.ctx,
            slot=slot + 1,
            selectors=(option,),
            use_search=self.use_search,
        )

    def _move_member(self, source: int, target: int) -> None:
        """把一艘舰船从源槽位拖到目标槽位，并同步内存顺序。

        Args:
            source: 零基源槽位序号。
            target: 零基目标槽位序号。
        """
        if source == target:
            return
        FleetSlotPage(self.ctx).drag_slot(source + 1, target + 1)
        report_progress(
            self.notify, 'ship_moved', {'source': source + 1, 'destination': target + 1}
        )
        self.current.insert(target, self.current.pop(source))
        time.sleep(REORDER_WAIT)

    def _build_state(self) -> planner.FleetState:
        """把当前字段打包成算法层的只读状态视图。

        Returns:
            当前对齐状态的只读快照。
        """
        return planner.FleetState(
            selectors=self.selectors,
            current=self.current,
            occupied=self.occupied,
            assigned=self.assigned,
            verified_slots=self.verified_slots,
            unavailable=self.unavailable,
            locked=self.locked,
            attempted=self.attempted,
        )

    def _mark_snapshot_verified_slots(self, snapshot: FleetSnapshot | None) -> None:
        """用首次快照标记已就位槽位，避免已选好的舰船再进一次船池。

        Args:
            snapshot: 进入本次对齐前的快照；没有快照时不标记。
        """
        if snapshot is None:
            return
        self.verified_slots.update(
            planner.build_snapshot_verified_slots(snapshot, self.assigned, self.verified_slots)
        )


__all__ = ['FleetAligner', 'UnresolvedPrimaryError']
