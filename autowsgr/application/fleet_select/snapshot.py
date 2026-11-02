"""模块功能：把准备页的识别原文比对成标准舰名，产出一次舰队快照。

上层调用：
- fleet_select.alignment：换船前后各读一次当前编队。

下层依赖：
- application.controller.sortie.battle_preparation.ship_recognition：读六槽舰名原文、
  舰种、等级与血条状态。
- fleet_select.names：舰名纠错规则、舰名清单与模糊匹配。
- fleet_select.constants：舰名模糊匹配阈值。

边界：只做舰名比对与快照组装，不判断阵容规则、不点击、不上报业务错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_recognition import (
    read_fleet_recognition,
)
from autowsgr.application.fleet_select.constants import (
    CONTEXT_MATCH_THRESHOLD,
    SHIP_FUZZY_THRESHOLD,
)
from autowsgr.application.fleet_select.models import FleetSnapshot
from autowsgr.application.fleet_select.names import (
    SHIPNAMES,
    apply_ship_name_corrections,
    fuzzy_match_ship_name,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.dispatch.context import ContextHandle


# ── 快照读取 ────────────────────────────────────────────────────────────────


def read_fleet_snapshot(
    ctx: ContextHandle,
    *,
    expected_slot_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
) -> FleetSnapshot:
    """读取准备页当前六个槽位的舰队事实快照。

    舰名比对分三档：先在全量舰名表里模糊匹配，再只在本槽目标名下匹配，
    最后在整个位置无关的目标池里匹配。后两档用来救 OCR 把舰名读歪的情况。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        expected_slot_names: 逐槽目标舰名，用于第二档比对；可缺省或为 None。
        expected_pool: 全部主选与备选组成的舰名池，用于第三档比对。

    Returns:
        六槽舰名、占用、舰种与等级的快照；识别不到的字段为空。
    """
    recognition = read_fleet_recognition(ctx)
    pool = list(expected_pool) if expected_pool else []
    return FleetSnapshot(
        names=tuple(
            _match_ship_name(
                text,
                _expected_name_at(expected_slot_names, slot),
                pool,
            )
            for slot, text in enumerate(recognition.name_texts)
        ),
        occupied=recognition.occupied,
        ship_types=recognition.ship_types,
        ship_levels=recognition.ship_levels,
    )


# ── 私有实现 ────────────────────────────────────────────────────────────────


def _expected_name_at(expected_slot_names: Sequence[str | None] | None, slot: int) -> str | None:
    """取某一槽位的目标舰名，未提供时返回 None。"""
    if expected_slot_names is None or slot >= len(expected_slot_names):
        return None
    return expected_slot_names[slot]


def _match_ship_name(text: str | None, expected_name: str | None, pool: list[str]) -> str | None:
    """把 OCR 原文按三档比对成标准舰名。"""
    if text is None:
        return None

    corrected = apply_ship_name_corrections(text)
    matched = fuzzy_match_ship_name(corrected, SHIPNAMES, threshold=SHIP_FUZZY_THRESHOLD)
    if matched is not None:
        return matched
    if expected_name is not None:
        matched = fuzzy_match_ship_name(
            corrected,
            [expected_name],
            threshold=CONTEXT_MATCH_THRESHOLD,
        )
        if matched is not None:
            return matched
    if pool:
        return fuzzy_match_ship_name(corrected, pool, threshold=CONTEXT_MATCH_THRESHOLD)
    return None


__all__ = ['read_fleet_snapshot']
