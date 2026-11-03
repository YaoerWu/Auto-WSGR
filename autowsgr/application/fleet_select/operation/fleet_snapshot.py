"""模块功能：识别准备页六个编队框，合成舰队快照。

上层调用：
- fleet_select.models：换船每一轮读取当前编队与最终位置。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition：四个识别入口。
- fleet_select.rules.ocr：把识别原文后处理成结构化事实。
- fleet_select.rules.shipnames：按舰名身份比对补识别结果。
- fleet_select.types：舰队快照数据契约。

边界：只读一次或多次页面事实并合并，不判断规则是否满足、不点击页面。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import (
    ShipDamage,
    read_ship_damage,
    read_ship_levels,
    read_ship_names,
    read_ship_types,
)
from autowsgr.application.fleet_select.rules.ocr import build_snapshot
from autowsgr.application.fleet_select.rules.shipnames import get_ship_name_identity
from autowsgr.application.fleet_select.types import FleetSnapshot


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from autowsgr.application.controller.types import ShipType
    from autowsgr.dispatch.context import ContextHandle


class DetailRequirement(NamedTuple):
    """补读某一舰名所需的舰种与等级。"""

    require_ship_type: bool
    require_ship_level: bool


# ── 读取 ────────────────────────────────────────────────────────────────────


def read_fleet_snapshot(
    ctx: ContextHandle,
    *,
    expected_slot_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
    include_details: bool = True,
) -> FleetSnapshot:
    """读取一帧准备页六槽事实。

    Args:
        ctx: 提供截图事实的 dispatch 上下文句柄。
        expected_slot_names: 逐槽目标舰名，用于第二档舰名补救匹配。
        expected_pool: 全部目标舰名，用于第三档舰名补救匹配。
        include_details: 是否同时读取舰种与等级；首帧只读舰名与占用。

    Returns:
        当前帧的舰队快照。
    """
    occupied = [state is not ShipDamage.NO_SHIP for state in read_ship_damage(ctx)]
    return build_snapshot(
        occupied=occupied,
        name_texts=read_ship_names(ctx),
        ship_type_texts=read_ship_types(ctx) if include_details else None,
        ship_level_texts=read_ship_levels(ctx) if include_details else None,
        expected_slot_names=expected_slot_names,
        expected_pool=expected_pool,
    )


def read_missing_details(
    ctx: ContextHandle,
    snapshot: FleetSnapshot,
    *,
    expected_pool: Sequence[str] | None = None,
    detail_requirements: Mapping[str, DetailRequirement] | None = None,
) -> FleetSnapshot:
    """重新截一帧，只补齐仍未确认的舰名字段与需要的舰种、等级。

    Args:
        ctx: 提供截图事实的 dispatch 上下文句柄。
        snapshot: 上一帧合并得到的舰队快照。
        expected_pool: 全部目标舰名，用于舰名补救匹配。
        detail_requirements: 舰名身份到补读需求的映射；不传时补齐所有未知细节。

    Returns:
        补识别后的舰队快照；没有可补的槽位时原样返回。
    """
    names = list(snapshot.names)
    ship_types = list(snapshot.ship_types or (None,) * len(names))
    ship_levels = list(snapshot.ship_levels or (None,) * len(names))

    def plan_detail_slots() -> tuple[list[int], list[int]]:
        """按舰名身份筛出本轮需要补读舰种与等级的槽位。

        Returns:
            需要补舰种的槽位与需要补等级的槽位，均为 0 基下标。
        """
        if detail_requirements is None:
            return list(snapshot.unknown_type_slots), list(snapshot.unknown_level_slots)
        type_slots: list[int] = []
        level_slots: list[int] = []
        for slot, (name, is_occupied) in enumerate(
            zip(names, snapshot.occupied, strict=True),
        ):
            identity = get_ship_name_identity(name)
            requirements = detail_requirements.get(identity) if identity is not None else None
            if not is_occupied or requirements is None:
                continue
            if requirements.require_ship_type and ship_types[slot] is None:
                type_slots.append(slot)
            if requirements.require_ship_level and ship_levels[slot] is None:
                level_slots.append(slot)
        return type_slots, level_slots

    unknown_slots = list(snapshot.unknown_slots)
    type_slots, level_slots = plan_detail_slots()
    if not unknown_slots and not type_slots and not level_slots:
        return snapshot

    fresh = read_fleet_snapshot(
        ctx,
        expected_slot_names=names,
        expected_pool=expected_pool,
    )
    for slot in unknown_slots:
        if fresh.names[slot] is not None:
            names[slot] = fresh.names[slot]

    # 舰名可能刚在这一帧识别成功，细节槽位要按新舰名重算一次。
    type_slots, level_slots = plan_detail_slots()
    for slot in type_slots:
        if fresh.ship_types is not None and fresh.ship_types[slot] is not None:
            ship_types[slot] = fresh.ship_types[slot]
    for slot in level_slots:
        if fresh.ship_levels is not None and fresh.ship_levels[slot] is not None:
            ship_levels[slot] = fresh.ship_levels[slot]

    return FleetSnapshot(
        names=tuple(names),
        occupied=snapshot.occupied,
        ship_types=tuple(ship_types),
        ship_levels=tuple(ship_levels),
    )


# ── 合并 ────────────────────────────────────────────────────────────────────


def build_merged_snapshot(
    current: Sequence[str | None],
    fresh: FleetSnapshot,
) -> tuple[list[str | None], list[bool]]:
    """用新一帧识别结果刷新槽位，识别不到的槽位保留已确认舰名。

    Args:
        current: 上一次确认的六槽舰名。
        fresh: 刚读出的一帧快照。

    Returns:
        合并后的六槽舰名与占用情况。
    """
    names: list[str | None] = []
    for confirmed, detected, is_occupied in zip(current, fresh.names, fresh.occupied, strict=True):
        if not is_occupied:
            names.append(None)
        elif detected is not None:
            names.append(detected)
        else:
            names.append(confirmed)
    return names, list(fresh.occupied)


def build_finished_snapshot(
    current: Sequence[str | None],
    occupied: Sequence[bool],
    initial: FleetSnapshot,
) -> FleetSnapshot:
    """用最终槽位与首帧舰种等级合成调用方要的完成快照。

    舰种与等级跟着舰船走，不跟着槽位走：对齐与换船都会移动船，直接按槽位搬首帧
    细节会张冠李戴。这里按舰名身份回填首帧的舰种与等级；换进来的船首帧没有记录，
    保持未确认。

    Args:
        current: 最终六槽舰名。
        occupied: 最终六槽占用情况。
        initial: 首帧快照，提供换船后未再重读的舰种与等级。

    Returns:
        换船完成后的舰队快照。
    """
    details: dict[str, tuple[ShipType | None, int | None]] = {}
    for slot, name in enumerate(initial.names):
        identity = get_ship_name_identity(name)
        if identity is None:
            continue
        details[identity] = (
            initial.ship_types[slot] if initial.ship_types else None,
            initial.ship_levels[slot] if initial.ship_levels else None,
        )

    ship_types: list[ShipType | None] = []
    ship_levels: list[int | None] = []
    for name in current:
        identity = get_ship_name_identity(name)
        ship_type, ship_level = details.get(identity, (None, None)) if identity else (None, None)
        ship_types.append(ship_type)
        ship_levels.append(ship_level)

    return FleetSnapshot(
        names=list(current),
        occupied=list(occupied),
        ship_types=tuple(ship_types),
        ship_levels=tuple(ship_levels),
    )


__all__ = [
    'DetailRequirement',
    'build_finished_snapshot',
    'build_merged_snapshot',
    'read_fleet_snapshot',
    'read_missing_details',
]
