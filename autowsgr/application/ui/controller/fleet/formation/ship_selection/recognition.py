"""模块功能：识别船池可见船卡并校验舰名、舰种和等级约束。

上层调用：
- ship_selection.workflow：提供截图和单条舰船选择规则。

下层依赖：
- ship_selection.constants：提供船卡扫描和 OCR 校准。
- common.constants、common.vision：提供舰名匹配、船卡定位和 OCR。

本文件只负责视觉识别和规则约束判断，不点击设备、不滚动列表、不决定候选顺序。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.vision.ocr_rules import get_user_ship_name_alias
from autowsgr.application.vision.ship_list import (
    LevelOCRRetryNeededError,
    extract_ship_type_from_text,
    locate_ship_rows,
    read_ship_level_at_card,
    recognize_card_type_texts,
)
from autowsgr.application.fleet_select.names import SHIPNAMES, normalize_ship_name
from autowsgr.common.vision import ocr


if TYPE_CHECKING:
    import numpy

    from autowsgr.application.controller.sortie.battle_preparation.ship_recognition.types import ShipType
    from autowsgr.common.vision import OCREngine


@dataclass(frozen=True, slots=True)
class _CardConstraintResult:
    """一张船卡的舰种、等级约束判断结果。"""

    accepted: bool
    type_unknown: bool = False
    level_unknown: bool = False
    retry_level_ocr: bool = False

    @property
    def is_fallback(self) -> bool:
        """判断该船卡是否只能作为宽松规则的后备候选。"""
        return self.type_unknown or self.level_unknown

    @property
    def fallback_priority(self) -> tuple[int, bool]:
        """返回宽松候选排序键，优先选择未知字段更少的船卡。"""
        return (
            int(self.type_unknown) + int(self.level_unknown),
            self.type_unknown,
        )


def _find_ship_card(
    ocr_engine: OCREngine,
    screen: numpy.ndarray,
    name: str,
    *,
    ship_types: tuple[ShipType, ...] | None = None,
    min_level: int | None = None,
    max_level: int | None = None,
    relaxed_constraints: bool = False,
) -> tuple[tuple[str, float, float] | None, bool]:
    """从当前可见船卡中查找满足规则的卡片，并返回等级 OCR 重试标记。"""
    use_level_filter = min_level is not None or max_level is not None
    use_card_constraints = ship_types is not None or use_level_filter
    extra_names = {'expected_names': (name,)} if name not in SHIPNAMES else {}
    raw_hits = locate_ship_rows(
        ocr_engine,
        screen,
        deduplicate_by_name=not use_card_constraints,
        include_row_key=use_card_constraints,
        **extra_names,
    )
    hits = [_normalize_hit_entry(hit) for hit in raw_hits]
    selected_hit: tuple[str, float, float] | None = None
    relaxed_hits: list[tuple[int, bool, int, tuple[str, float, float]]] = []
    retry_level_ocr = False

    for hit_index, (matched, cx, cy, row_key) in enumerate(hits):
        if not _matches_ship_name(name, matched):
            continue
        constraint = _check_hit_constraints(
            ocr_engine,
            screen,
            cx,
            cy,
            row_key,
            ship_types=ship_types,
            min_level=min_level,
            max_level=max_level,
            relaxed_constraints=relaxed_constraints,
        )
        retry_level_ocr = retry_level_ocr or constraint.retry_level_ocr
        if not constraint.accepted:
            continue
        hit = (matched, cx, cy)
        if constraint.is_fallback:
            relaxed_hits.append(
                (
                    *constraint.fallback_priority,
                    hit_index,
                    hit,
                ),
            )
            continue
        selected_hit = hit
        break

    if selected_hit is None and relaxed_hits:
        selected_hit = min(relaxed_hits, key=lambda candidate: candidate[:3])[3]
    return selected_hit, retry_level_ocr


def _normalize_hit_entry(hit: object) -> tuple[str, float, float, float]:
    """将船卡定位结果归一化为名称、中心坐标和行坐标。"""
    if not isinstance(hit, (tuple, list)) or len(hit) < 3:
        raise ValueError(f'unsupported ship card hit: {hit!r}')
    matched = str(hit[0]).strip()
    center_x = float(hit[1])
    center_y = float(hit[2])
    row_key = (
        round(float(hit[3]), 4)
        if len(hit) >= 4 and isinstance(hit[3], (int, float))
        else round(center_y, 4)
    )
    return matched, center_x, center_y, row_key


def _check_hit_constraints(
    ocr_engine: OCREngine,
    screen: numpy.ndarray,
    center_x: float,
    center_y: float,
    row_key: float,
    *,
    ship_types: tuple[ShipType, ...] | None,
    min_level: int | None,
    max_level: int | None,
    relaxed_constraints: bool,
) -> _CardConstraintResult:
    """按舰种、等级顺序校验一张船卡。"""
    type_unknown = False
    if ship_types is not None:
        detected_ship_type = _detect_ship_type_in_card(
            ocr_engine,
            screen,
            center_x,
            center_y,
            row_key,
        )
        if detected_ship_type is None:
            if not relaxed_constraints:
                return _CardConstraintResult(accepted=False)
            type_unknown = True
        elif not _is_ship_type_in_rule(detected_ship_type, ship_types):
            return _CardConstraintResult(accepted=False)

    level_unknown = False
    retry_level_ocr = False
    if min_level is not None or max_level is not None:
        try:
            level = read_ship_level_at_card(
                ocr_engine,
                screen,
                card_x=center_x,
                row_key=row_key,
            )
        except LevelOCRRetryNeededError:
            retry_level_ocr = True
            level = None

        if level is None:
            if not relaxed_constraints:
                return _CardConstraintResult(
                    accepted=False,
                    retry_level_ocr=retry_level_ocr,
                )
            level_unknown = True
        elif not _is_level_in_range(level, min_level, max_level):
            return _CardConstraintResult(accepted=False)

    return _CardConstraintResult(
        accepted=True,
        type_unknown=type_unknown,
        level_unknown=level_unknown,
        retry_level_ocr=retry_level_ocr,
    )


def _detect_ship_type_in_card(
    ocr_engine: OCREngine,
    screen: numpy.ndarray,
    center_x: float,
    center_y: float,
    row_key: float,
) -> ShipType | None:
    """以船名位置为锚点读取单张船卡舰种。"""
    for _scale, results in recognize_card_type_texts(
        ocr_engine,
        screen,
        card_x=center_x,
        card_y=center_y,
        row_key=row_key,
    ):
        detected_types: set[ShipType] = set()
        for result in results:
            ship_type = _extract_ship_type_from_text(str(getattr(result, 'text', '')))
            if ship_type is not None:
                detected_types.add(ship_type)
        if len(detected_types) == 1:
            return next(iter(detected_types))
        if len(detected_types) > 1:
            return None
    return None


def _extract_ship_type_from_text(text: str) -> ShipType | None:
    """从 OCR 文本中提取舰种。"""
    return extract_ship_type_from_text(text)


def _is_ship_type_in_rule(
    detected: ShipType | None,
    expected: tuple[ShipType, ...],
) -> bool:
    """判断 OCR 识别出的舰种是否属于规则允许集合。"""
    return detected is not None and detected in expected


def _is_level_in_range(
    level: int | None,
    min_level: int | None,
    max_level: int | None,
) -> bool:
    """判断识别等级是否落在规则指定范围内。"""
    if min_level is None and max_level is None:
        return True
    if level is None:
        return False
    if min_level is not None and level < min_level:
        return False
    return max_level is None or level <= max_level


def _normalize_search_keyword(name: str) -> str:
    """将目标舰名转换为游戏搜索框可识别的名称。"""
    text = name.strip()
    return get_user_ship_name_alias(text) or text


def _matches_ship_name(target: str, matched: str) -> bool:
    """比较目标舰名与 OCR 船卡名称，不修改原始文本。"""
    normalized_target = normalize_ship_name(target)
    normalized_matched = normalize_ship_name(matched)
    if normalized_target == normalized_matched:
        return True
    pool_target = ocr._fuzzy_match(target, SHIPNAMES, threshold=0)
    return pool_target is not None and normalize_ship_name(pool_target) == normalized_matched


__all__ = []
