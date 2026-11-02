"""模块功能：识别准备页当前编队的舰名、槽位、舰种和等级事实。

上层调用：
- formation.workflow：提供编队调整前后的截图和目标规则上下文。

下层依赖：
- formation.fleet_recognition.constants：提供舰名、槽位和文字 ROI。
- formation.fleet_recognition.models：保存识别快照。
- common.vision：执行截图裁剪、像素占用识别和 OCR。

本模块只接收截图和显式 OCR 引擎，不创建上下文、不点击设备、不决定编队调整。
现有舰名 OCR 依赖 common.vision.ocr 的内部匹配函数，留给 OCR 专题处理。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.fleet.formation.fleet_recognition import constants
from autowsgr.application.ui.controller.fleet.formation.fleet_recognition.models import (
    FleetSnapshot,
)
from autowsgr.application.ui.controller.fleet.main_page.constants import BLOOD_BAR_PROBE
from autowsgr.application.ui.ships.types import ShipType
from autowsgr.application.vision.damage_recognition import classify_blood
from autowsgr.application.vision.ocr_rules import LEVEL_OCR_ALLOWLIST
from autowsgr.application.vision.ship_list import (
    best_fleet_level,
    extract_ship_type_from_text,
    parse_fleet_level,
    prepare_level_crop,
    upscale_text_crop,
)
from autowsgr.application.vision.shipnames import SHIPNAMES, normalize_ship_name, ship_name_identity
from autowsgr.business.logistics.types import ShipDamageState
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import PixelChecker, ocr


if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    import numpy

    from autowsgr.common.vision import OCREngine


_log = get_logger('ui.fleet.formation.fleet_recognition')


# ── OCR 识别参数 ─────────────────────────────────────────────────────────────

SHIP_TYPE_SCALE = 4  # 舰种文字放大倍数，用于提高准备页小字号 OCR 的可读性。
CONTEXT_MATCH_THRESHOLD = 3  # 目标舰名上下文匹配允许的最大差异，用于处理槽位 OCR 噪声。


# ── 编队占用识别 ─────────────────────────────────────────────────────────────


def read_fleet_occupancy(screen: numpy.ndarray) -> dict[int, bool]:
    """读取六个物理槽位是否存在舰船。

    Args:
        screen: 准备页 RGB 截图。

    Returns:
        槽位号到占用状态的映射；空槽为 False。
    """
    return {
        slot: classify_blood(PixelChecker.get_pixel(screen, *probe)) is not ShipDamageState.NO_SHIP
        for slot, probe in BLOOD_BAR_PROBE.items()
    }


# ── 舰名识别 ─────────────────────────────────────────────────────────────────


def read_fleet_names(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    *,
    expected_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
) -> list[str | None]:
    """从准备页截图读取六个槽位的舰名。

    Args:
        screen: 准备页 RGB 截图。
        ocr_engine: 调用方注入的 OCR 引擎。
        expected_names: 按物理槽位排列的目标舰名，用于槽位内消歧。
        expected_pool: 本轮允许作为补救匹配的目标舰名集合。

    Returns:
        按物理槽位排列的舰名；未识别或空槽为 None。
    """
    height, width = screen.shape[:2]
    y1 = int(constants.FLEET_NAME_STRIP_Y[0] * height)
    y2 = int(constants.FLEET_NAME_STRIP_Y[1] * height)
    strip = screen[y1:y2, :]
    results = sorted(
        ocr_engine.recognize(strip),
        key=lambda result: (
            (result.bbox[0] + result.bbox[2]) / 2 if result.bbox is not None else float('inf')
        ),
    )

    expected_slots = (
        [normalize_ship_name(name) for name in list(expected_names)[:6]]
        if expected_names is not None
        else []
    )
    expected_slots += [None] * (6 - len(expected_slots))
    normalized_pool = [
        normalized
        for name in dict.fromkeys(expected_pool or ())
        if (normalized := normalize_ship_name(name)) is not None
    ]

    ships: list[str | None] = [None] * 6
    recognized_ocr: list[dict[str, object]] = []
    for result in results:
        raw_text = result.text.strip()
        if not raw_text or result.bbox is None:
            continue
        patched_text = ocr.apply_ship_patches(raw_text)
        pool_match = ocr._fuzzy_match(
            patched_text,
            SHIPNAMES,
            constants.SHIP_FUZZY_THRESHOLD,
        )
        cx_rel = (result.bbox[0] + result.bbox[2]) / 2 / width
        slot = min(
            range(6),
            key=lambda index, center=cx_rel: abs(constants.FLEET_SLOT_X_CENTERS[index] - center),
        )
        matched = pool_match
        expected_name = expected_slots[slot]
        if expected_name is not None and matched is None:
            matched = _match_context_ship_name(patched_text, [expected_name])
        elif matched is None and normalized_pool:
            matched = _match_context_ship_name(patched_text, normalized_pool)
        recognized_ocr.append(
            {
                'physical_slot': slot + 1,
                'raw': raw_text,
                'patched': patched_text,
                'matched': matched,
                'confidence': result.confidence,
                'bbox': result.bbox,
            },
        )
        if matched is not None:
            ships[slot] = matched

    _log.debug('[Fleet] 舰名 OCR 原始及后处理: {}', recognized_ocr)
    _log.debug('[Fleet] 舰名 OCR 后处理编队: {}', ships)
    return ships


def _match_context_ship_name(
    text: str,
    expected_names: Sequence[str | None],
) -> str | None:
    """在指定目标集合中执行唯一上下文匹配。"""
    candidates = [
        name.strip()
        for name in dict.fromkeys(expected_names)
        if isinstance(name, str) and name.strip()
    ]
    if not text or not candidates:
        return None
    matched = ocr._fuzzy_match(
        ocr.apply_ship_patches(text),
        candidates,
        threshold=CONTEXT_MATCH_THRESHOLD,
    )
    if matched is not None:
        _log.debug("[Fleet] 目标槽位匹配: '{}' -> '{}'", text, matched)
    return matched


def _read_fleet_names_at_slots(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    slots: Sequence[int],
    *,
    expected_pool: Sequence[str] | None = None,
) -> dict[int, str | None]:
    """只裁切并识别指定物理槽位的舰名。"""
    target_slots = sorted(set(slots))
    names: dict[int, str | None] = dict.fromkeys(target_slots)
    normalized_pool = [
        normalized
        for name in dict.fromkeys(expected_pool or ())
        if (normalized := normalize_ship_name(name)) is not None
    ]
    height, width = screen.shape[:2]
    y1 = int(constants.FLEET_NAME_STRIP_Y[0] * height)
    y2 = int(constants.FLEET_NAME_STRIP_Y[1] * height)

    for slot in target_slots:
        if not 0 <= slot < len(constants.FLEET_SLOT_X_CENTERS):
            continue
        center = constants.FLEET_SLOT_X_CENTERS[slot]
        left_center = constants.FLEET_SLOT_X_CENTERS[max(slot - 1, 0)]
        right_center = constants.FLEET_SLOT_X_CENTERS[min(slot + 1, 5)]
        left = center - (right_center - center) / 2 if slot == 0 else (left_center + center) / 2
        right = center + (center - left_center) / 2 if slot == 5 else (center + right_center) / 2
        crop = screen[y1:y2, max(0, int(left * width)) : min(width, int(right * width))]
        results = [item for item in ocr_engine.recognize(crop) if item.text.strip()]
        if not results:
            continue
        result = max(results, key=lambda item: item.confidence)
        patched_text = ocr.apply_ship_patches(result.text.strip())
        matched = ocr._fuzzy_match(
            patched_text,
            SHIPNAMES,
            constants.SHIP_FUZZY_THRESHOLD,
        )
        if matched is None and normalized_pool:
            matched = _match_context_ship_name(patched_text, normalized_pool)
        names[slot] = matched
    return names


# ── 舰种和等级识别 ───────────────────────────────────────────────────────────


def read_fleet_levels(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    slots: Collection[int] | None = None,
) -> dict[int, int | None]:
    """从准备页舰船卡片 OCR 读取指定槽位等级。"""
    target_slots = list(range(6)) if slots is None else sorted(set(slots))
    levels: dict[int, int | None] = dict.fromkeys(target_slots)
    for slot in target_slots:
        crop_region = constants.SHIP_LEVEL_CROP.get(slot)
        if crop_region is None:
            continue
        prepared = prepare_level_crop(PixelChecker.crop(screen, *crop_region))
        results = ocr_engine.recognize_line(
            prepared,
            allowlist=LEVEL_OCR_ALLOWLIST,
        )
        levels[slot] = _best_level_from_results(results)
    return levels


def read_fleet_ship_types(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    slots: Collection[int] | None = None,
) -> dict[int, ShipType | None]:
    """从准备页舰船卡片 OCR 读取指定槽位舰种。"""
    target_slots = list(range(6)) if slots is None else sorted(set(slots))
    ship_types: dict[int, ShipType | None] = dict.fromkeys(target_slots)
    for slot in target_slots:
        crop_region = constants.SHIP_TYPE_CROP.get(slot)
        if crop_region is None:
            continue
        cropped = PixelChecker.crop(screen, *crop_region)
        results = ocr_engine.recognize(upscale_text_crop(cropped, SHIP_TYPE_SCALE))
        ship_types[slot] = _best_ship_type_from_results(results)
    return ship_types


def _best_ship_type_from_results(results: list) -> ShipType | None:
    """从 OCR 结果中提取唯一舰种，冲突时返回 None。"""
    detected: ShipType | None = None
    for result in results:
        text = str(getattr(result, 'text', '')).strip()
        if not text:
            continue
        ship_type = extract_ship_type_from_text(text)
        if ship_type is None:
            continue
        if detected is not None and detected != ship_type:
            return None
        detected = ship_type
    return detected


def _parse_level(text: str) -> int | None:
    """解析 OCR 返回的舰船等级文本。"""
    return parse_fleet_level(text)


def _best_level_from_results(results: list) -> int | None:
    """从 OCR 结果中选取可信的舰船等级。"""
    return best_fleet_level(results)


# ── 快照入口 ─────────────────────────────────────────────────────────────────


def read_fleet_snapshot(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    *,
    expected_names: Sequence[str | None] | None = None,
    expected_pool: Sequence[str] | None = None,
    recognize_ship_details: bool = False,
) -> FleetSnapshot:
    """使用同一截图读取当前编队快照。

    Args:
        screen: 准备页 RGB 截图。
        ocr_engine: 调用方注入的 OCR 引擎。
        expected_names: 按槽位排列的目标舰名，用于舰名消歧。
        expected_pool: 本轮目标舰名集合，用于 OCR 补救。
        recognize_ship_details: 是否额外读取舰种和等级。

    Returns:
        当前六个物理槽位的舰名、占用、舰种和等级事实。
    """
    names = read_fleet_names(
        screen,
        ocr_engine,
        expected_names=expected_names,
        expected_pool=expected_pool,
    )
    occupancy = read_fleet_occupancy(screen)
    occupied = [names[slot] is not None or occupancy.get(slot, False) for slot in range(6)]
    if not recognize_ship_details:
        return FleetSnapshot(names=names, occupied=occupied)

    unknown_name_slots = [slot for slot in range(6) if occupied[slot] and names[slot] is None]
    if unknown_name_slots:
        names_by_slot = _read_fleet_names_at_slots(
            screen,
            ocr_engine,
            unknown_name_slots,
            expected_pool=expected_pool,
        )
        for slot in unknown_name_slots:
            if names_by_slot.get(slot) is not None:
                names[slot] = names_by_slot[slot]

    occupied_slots = [slot for slot in range(6) if occupied[slot]]
    types_by_slot = read_fleet_ship_types(screen, ocr_engine, occupied_slots)
    levels_by_slot = read_fleet_levels(screen, ocr_engine, occupied_slots)
    return FleetSnapshot(
        names=names,
        occupied=occupied,
        ship_types=[types_by_slot.get(slot) for slot in range(6)],
        ship_levels=[levels_by_slot.get(slot) for slot in range(6)],
    )


def fill_missing_fleet_snapshot(
    screen: numpy.ndarray,
    ocr_engine: OCREngine,
    snapshot: FleetSnapshot,
    *,
    expected_pool: Sequence[str] | None = None,
    detail_requirements: Mapping[str, tuple[bool, bool]] | None = None,
    recognize_ship_types: bool = True,
) -> FleetSnapshot:
    """在新截图中只补充快照尚未确认的字段。"""
    names = list(snapshot.names)
    ship_types = list(snapshot.ship_types or [None] * 6)
    ship_levels = list(snapshot.ship_levels or [None] * 6)

    def required_detail_slots() -> tuple[list[int], list[int]]:
        if detail_requirements is None:
            type_slots = snapshot.unknown_type_slots if recognize_ship_types else []
            return type_slots, snapshot.unknown_level_slots

        type_slots: list[int] = []
        level_slots: list[int] = []
        for slot, (name, occupied) in enumerate(
            zip(names, snapshot.occupied, strict=True),
        ):
            identity = ship_name_identity(name)
            requirements = detail_requirements.get(identity) if identity is not None else None
            if not occupied or requirements is None:
                continue
            needs_type, needs_level = requirements
            if recognize_ship_types and needs_type and ship_types[slot] is None:
                type_slots.append(slot)
            if needs_level and ship_levels[slot] is None:
                level_slots.append(slot)
        return type_slots, level_slots

    type_slots, level_slots = required_detail_slots()
    if not snapshot.unknown_slots and not type_slots and not level_slots:
        return snapshot

    if snapshot.unknown_slots:
        names_by_slot = _read_fleet_names_at_slots(
            screen,
            ocr_engine,
            snapshot.unknown_slots,
            expected_pool=expected_pool,
        )
        for slot in snapshot.unknown_slots:
            if names_by_slot.get(slot) is not None:
                names[slot] = names_by_slot[slot]

    type_slots, level_slots = required_detail_slots()
    if type_slots:
        types_by_slot = read_fleet_ship_types(screen, ocr_engine, type_slots)
        for slot in type_slots:
            if types_by_slot.get(slot) is not None:
                ship_types[slot] = types_by_slot[slot]
    if level_slots:
        levels_by_slot = read_fleet_levels(screen, ocr_engine, level_slots)
        for slot in level_slots:
            if levels_by_slot.get(slot) is not None:
                ship_levels[slot] = levels_by_slot[slot]

    return FleetSnapshot(
        names=names,
        occupied=list(snapshot.occupied),
        ship_types=ship_types,
        ship_levels=ship_levels,
    )


__all__ = [
    'FleetSnapshot',
    'fill_missing_fleet_snapshot',
    'read_fleet_levels',
    'read_fleet_names',
    'read_fleet_occupancy',
    'read_fleet_ship_types',
    'read_fleet_snapshot',
]
