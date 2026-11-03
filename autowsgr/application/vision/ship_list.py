"""选船列表 DLL 行定位 + OCR 识别。

普通出征换船和决战换船共用的 DLL 行定位、图像预处理和 OCR 原语。
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

import cv2

from autowsgr.application.fleet_select.rules.shipnames import (
    SHIPNAMES,
    build_ship_name_candidates,
    normalize_ship_name,
)
from autowsgr.application.vision.calibration.choose_ship import (
    CARD_REFERENCE_HEIGHT,
    CARD_REFERENCE_WIDTH,
    LEGACY_HEIGHT,
    LEGACY_LIST_WIDTH,
    LEGACY_WIDTH,
    SHIP_LEVEL_CROP_OFFSETS,
    SHIP_LEVEL_OCR_SCALES,
)
from autowsgr.application.vision.native import get_api_dll
from autowsgr.application.vision.ocr_rules import (
    LEVEL_DIGIT_CONFUSABLES,
    LEVEL_OCR_ALLOWLIST,
    SHIP_TYPE_OCR_ALLOWLIST,
    apply_ship_name_rules,
    is_valid_ship_level,
    normalize_level_digits,
)
from autowsgr.application.vision.ocr_rules import (
    LEVEL_NOISY_PATTERN as _LEVEL_NOISY_PATTERN,
)
from autowsgr.application.vision.ocr_rules import (
    LEVEL_PATTERN as _LEVEL_PATTERN,
)
from autowsgr.application.vision.ocr_rules import (
    LEVEL_SHORT_PATTERN as _LEVEL_SHORT_PATTERN,
)
from autowsgr.common import vision
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import ShipType


if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import numpy as np


_log = get_logger('ui')

# 110 在 720p 下常被识别为 ``Il0`` / ``ll0``，其中两个 1 都会成为易混淆字符。
_MAX_LEVEL_NOISE_CHARS = 2
_MAX_NOISY_LEVEL_HITS_BEFORE_RETRY = 5
_MIN_SPLIT_LEVEL_CONFIDENCE = 0.85
_MIN_CUSTOM_NAME_BASE_LENGTH = 2
_MIN_TRUNCATED_OCR_LENGTH = 4
_MIN_FRAGMENT_OCR_LENGTH = 4


def _read_results(
    reader: object,
    image: np.ndarray,
    *,
    line: bool = False,
    allowlist: str = '',
) -> list[vision.OCRItem]:
    """通过 common vision 门面读取 OCR 结果。"""
    mode = vision.ReadMode.LINES if line else vision.ReadMode.TEXT
    return list(vision.read(image, reader=reader, mode=mode, allowlist=allowlist).items)


def apply_ship_patches(text: str) -> str:
    """应用舰名 OCR 纠错规则。"""
    return apply_ship_name_rules(text)


def set_ship_name_match_confidence(threshold: float) -> None:
    """设置舰名池匹配的最低置信度。"""
    global _ship_name_match_confidence  # noqa: PLW0603
    _ship_name_match_confidence = max(0.0, min(1.0, threshold))


_ship_name_match_confidence = 0.0


def extract_ship_type_from_text(text: str) -> ShipType | None:
    """Extract a ship type enum from OCR text."""
    if not text:
        return None
    normalized = re.sub(r'[（(][^（()）]*[)）]', '', text).replace(' ', '')
    for ship_type in ShipType:
        if ship_type is not ShipType.Other and ship_type.value in normalized:
            return ship_type
    return None


def upscale_text_crop(screen: np.ndarray, scale: int) -> np.ndarray:
    """使用统一插值放大 OCR 文本区域。"""
    return cv2.resize(screen, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def prepare_level_crop(screen: np.ndarray, scale: int = 2) -> np.ndarray:
    """放大并二值化等级文本区域。"""
    enlarged = upscale_text_crop(screen, scale)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_RGB2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)


def recognize_card_type_texts(
    ocr: object,
    screen: np.ndarray,
    *,
    card_x: float,
    card_y: float,
    row_key: float,
) -> Iterator[tuple[int, list[vision.OCRItem]]]:
    """读取单张船卡的舰种 OCR 文本。"""
    from autowsgr.application.vision.calibration.choose_ship import (
        SHIP_TYPE_CROP_OFFSETS,
        SHIP_TYPE_OCR_SCALES,
    )

    h, w = screen.shape[:2]
    x_px = max(0, min(w - 1, round(card_x * w)))
    y_px = max(0, min(h - 1, round(card_y * h)))
    row_y = max(0, min(h - 1, round(row_key * h))) if row_key >= 0 else y_px

    left, top, right, bottom = SHIP_TYPE_CROP_OFFSETS
    x1 = max(0.0, min(float(w), x_px + left * w / CARD_REFERENCE_WIDTH))
    x2 = max(0.0, min(float(w), x_px + right * w / CARD_REFERENCE_WIDTH))
    y1 = max(0.0, min(float(h), row_y + top * h / CARD_REFERENCE_HEIGHT))
    y2 = max(0.0, min(float(h), row_y + bottom * h / CARD_REFERENCE_HEIGHT))
    if x2 - x1 < 16 or y2 - y1 < 16:
        return

    source_x1 = math.floor(x1)
    source_x2 = math.ceil(x2)
    source_y1 = math.floor(y1)
    source_y2 = math.ceil(y2)
    source_crop = screen[source_y1:source_y2, source_x1:source_x2]
    for scale in SHIP_TYPE_OCR_SCALES:
        enlarged_source = cv2.resize(
            source_crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        crop_x1 = round((x1 - source_x1) * scale)
        crop_x2 = round((x2 - source_x1) * scale)
        crop_y1 = round((y1 - source_y1) * scale)
        crop_y2 = round((y2 - source_y1) * scale)
        enlarged = enlarged_source[crop_y1:crop_y2, crop_x1:crop_x2]
        results = _read_results(
            ocr,
            enlarged,
            line=True,
            allowlist=SHIP_TYPE_OCR_ALLOWLIST,
        )
        yield scale, results


class LevelOCRRetryNeededError(RuntimeError):
    """等级 OCR 噪声过高，需要重新截图识别。"""


def to_legacy_format(screen: np.ndarray) -> tuple[np.ndarray, float, float]:
    """将 V2 截图转为 DLL 所需的 legacy 格式。

    DLL 内部基于 1280x720 BGR 图像校准，V2 ``screenshot()``
    返回模拟器原生分辨率的 RGB 图像，需做两步转换。

    Returns
    -------
    tuple[np.ndarray, float, float]
        ``(bgr_720p, scale_y, scale_x)``
        -- bgr_720p: 1280x720 BGR 图像
        -- scale_y / scale_x: legacy 坐标 -> 原始坐标的缩放比
    """
    h, w = screen.shape[:2]
    scale_y = h / LEGACY_HEIGHT
    scale_x = w / LEGACY_WIDTH
    resized = cv2.resize(screen, (LEGACY_WIDTH, LEGACY_HEIGHT))
    bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
    return bgr, scale_y, scale_x


def _match_ship_results(
    results: list[vision.OCRItem],
    candidates: Sequence[str] = (),
) -> list[tuple[vision.OCRItem, str]]:
    """返回 OCR 结果中能够安全映射到唯一标准舰名的项目。"""
    names = [*SHIPNAMES, *candidates]
    matches: list[tuple[vision.OCRItem, str]] = []
    for result in results:
        text = result.text.strip()
        if not text:
            continue
        name = _fuzzy_match(apply_ship_patches(text), names)
        if name is not None:
            matches.append((result, name))
    return matches


def locate_ship_rows(
    ocr: object,
    screen: np.ndarray,
    *,
    deduplicate_by_name: bool = True,
    include_row_key: bool = False,
    expected_names: Sequence[str] = (),
) -> list[tuple[str, float, float] | tuple[str, float, float, float]]:
    """在选船列表页用 DLL 定位舰船名行，再逐行 OCR 识别。

    其他场景 (如 ``_click_ship_in_list``, ``recognize_ships_in_list``)
    应复用此函数而非重复实现 OCR 逻辑。

    对齐 legacy ``recognize_ship``:

    1. resize + RGB->BGR 转为 1280x720 BGR (DLL 校准基准)
    2. 裁剪左侧 1048px (与 legacy ``screen[:, :1048]`` 一致)
    3. ``dll.locate()`` 定位行区域
    4. 将行坐标映射回原始分辨率, 在原图上裁剪并 OCR

    Parameters
    ----------
    ocr:
        OCR 引擎实例。
    screen:
        选船列表页面的 V2 截图 (RGB, 任意分辨率)。
    deduplicate_by_name:
        是否按舰船名去重。默认 ``True`` 以保持兼容。
        在同名多行场景下可设为 ``False`` 保留全部命中。
    include_row_key:
        是否在返回值中附带行标识 (row_key)。默认 ``False``。
    expected_names:
        当前任务的额外目标名称。用于支持尚未进入内置船池的任务舰名；
        不改变全局船名表。

    Returns
    -------
    list[tuple[str, float, float] | tuple[str, float, float, float]]
        默认返回 ``(ship_name, cx_rel, cy_rel)``。
        当 ``include_row_key=True`` 时返回
        ``(ship_name, cx_rel, cy_rel, row_key)``。
        ``row_key`` 用于与等级识别结果做行级关联。
    """
    h, w = screen.shape[:2]

    # 转为 legacy 格式 (1280x720, BGR)
    bgr_720p, scale_y, _scale_x = to_legacy_format(screen)
    list_720p = bgr_720p[:, :LEGACY_LIST_WIDTH]  # legacy 裁剪宽度

    dll = get_api_dll()
    rows = dll.locate(list_720p)
    _log.debug('[选船列表] DLL 定位到 {} 行候选项', len(rows))

    # 在原始分辨率上裁剪并 OCR (用原图的左 82% 区域)
    list_w_native = int(w * LEGACY_LIST_WIDTH / LEGACY_WIDTH)
    list_area_native = screen[:, :list_w_native]

    found: list[tuple[str, float, float] | tuple[str, float, float, float]] = []
    seen: set[str] = set()
    for y_start_720, y_end_720 in rows:
        # 将 720p 坐标映射回原始分辨率
        y_start = max(0, int((y_start_720 - 1) * scale_y))
        y_end = min(h, int((y_end_720 + 1) * scale_y))

        row_img = list_area_native[y_start:y_end]

        # 对齐 legacy: recognize(multiple=True) -- 同一 DLL 行可含多个舰船名
        results = _read_results(ocr, row_img)
        matched_results = _match_ship_results(results, expected_names)
        upscaled_results: list[vision.OCRItem] = []
        result_scale = 1.0

        # 原图没有可靠舰名时才放大重试，避免增加正常识别路径的耗时。
        if not matched_results:
            upscaled = cv2.resize(
                row_img,
                None,
                fx=2,
                fy=2,
                interpolation=cv2.INTER_CUBIC,
            )
            upscaled_results = _read_results(ocr, upscaled)
            matched_results = _match_ship_results(upscaled_results, expected_names)
            result_scale = 2.0

        _log.debug(
            '[选船列表] 舰名OCR原始及后处理: row={} raw={} upscaled={} matched={}',
            (y_start_720, y_end_720),
            results,
            upscaled_results,
            [name for _, name in matched_results],
        )
        for r, name in matched_results:
            if deduplicate_by_name and name in seen:
                continue
            if deduplicate_by_name:
                seen.add(name)
            # 从 bbox 计算精确位置 (bbox 相对于 row_img)
            if r.bbox is not None:
                x1, y1, x2, y2 = r.bbox
                cx = (x1 + x2) / 2 / result_scale / w
                cy = (y_start + (y1 + y2) / 2 / result_scale) / h
            else:
                cx = list_w_native / 2 / w
                cy = (y_start + y_end) / 2 / h
            row_key = round((y_start + y_end) / 2 / h, 4)
            if include_row_key:
                found.append((name, cx, cy, row_key))
            else:
                found.append((name, cx, cy))

    _log.debug(
        '[选船列表] 识别: {} (共 {} 行)',
        sorted({entry[0] for entry in found}),
        len(rows),
    )
    return found


def recognize_ships_in_list(
    ocr: object,
    screen: np.ndarray,
) -> set[str]:
    """识别选船列表页面中的所有可见舰船名 (去重集合)。

    基于 :func:`locate_ship_rows` 的薄封装。
    """
    return {entry[0] for entry in locate_ship_rows(ocr, screen)}


class ShipNameMismatchError(ValueError):
    """OCR 文本与所有候选舰名的距离都超过硬阈值。"""

    def __init__(
        self,
        text: str,
        best_candidate: str,
        distance: int,
        max_threshold: int,
    ) -> None:
        self.text = text
        self.best_candidate = best_candidate
        self.distance = distance
        self.max_threshold = max_threshold
        super().__init__(
            f'OCR 识别到 {text!r}，与最近候选 {best_candidate!r} 编辑距离={distance} '
            f'超过最大阈值 {max_threshold}，拒绝匹配',
        )


def recognize_ship_name(
    screen: np.ndarray,
    ocr: object,
    candidates: Sequence[str] | None = None,
    threshold: int = 3,
) -> str | None:
    """读取单个舰名并匹配到候选舰名。"""
    results = _read_results(ocr, screen)
    if not results:
        return None
    result = max(results, key=lambda item: item.confidence)
    text = apply_ship_patches(result.text.strip())
    return _fuzzy_match(text, list(candidates) if candidates is not None else SHIPNAMES, threshold)


def recognize_ship_names(
    screen: np.ndarray,
    ocr: object,
    candidates: Sequence[str] | None = None,
    threshold: int = 3,
    max_threshold: int | None = None,
) -> list[str]:
    """读取多个舰名并按图像顺序去重返回。"""
    names = list(candidates) if candidates is not None else SHIPNAMES
    matched: list[str] = []
    seen: set[str] = set()
    for result in _read_results(ocr, screen):
        text = apply_ship_patches(result.text.strip())
        if not text:
            continue
        name = _fuzzy_match(text, names, threshold)
        if name is None:
            if max_threshold is not None and names:
                best_candidate = min(names, key=lambda candidate: _edit_distance(text, candidate))
                distance = _edit_distance(text, best_candidate)
                if distance > max_threshold:
                    raise ShipNameMismatchError(text, best_candidate, distance, max_threshold)
            continue
        if name not in seen:
            seen.add(name)
            matched.append(name)
    return matched


def _fuzzy_match(
    text: str,
    candidates: Sequence[str],
    threshold: int = 3,
) -> str | None:
    """按唯一编辑距离匹配舰名，无法确认时拒绝猜测。"""
    unique_candidates = list(dict.fromkeys(build_ship_name_candidates(list(candidates))))
    if not text or not unique_candidates:
        return None

    if _ship_name_match_confidence > 0.0:
        pool_name, handled = _fuzzy_match_pool_aware(
            text,
            unique_candidates,
            _ship_name_match_confidence,
        )
        if handled:
            return normalize_ship_name(pool_name)

    effective_threshold = (
        0 if len(text) == 1 else min(threshold, 1) if len(text) <= 3 else threshold
    )
    distances = [(name, _edit_distance(text, name)) for name in unique_candidates]
    best_dist = min(distance for _, distance in distances)
    nearest = list(
        dict.fromkeys(
            normalize_ship_name(name) for name, distance in distances if distance == best_dist
        ),
    )
    if len(nearest) == 1 and best_dist <= effective_threshold:
        return nearest[0]
    return None


def _fuzzy_match_pool_aware(  # noqa: PLR0911
    text: str,
    candidates: Sequence[str],
    confidence_threshold: float,
) -> tuple[str | None, bool]:
    """处理精确名称、明确后缀和唯一长名称片段。"""
    exact = [name for name in candidates if name == text]
    if exact:
        return normalize_ship_name(exact[0]), True

    if any(len(name) == 1 and text.startswith(f'{name}·') for name in candidates):
        return None, True

    custom_suffix_matches = [
        name
        for name in candidates
        if len(name) >= _MIN_CUSTOM_NAME_BASE_LENGTH and text.startswith(f'{name}·')
    ]
    truncated_matches = [
        name
        for name in candidates
        if len(text) >= _MIN_TRUNCATED_OCR_LENGTH and name.startswith(text)
    ]
    fragment_matches = [
        name
        for name in candidates
        if len(text) >= _MIN_FRAGMENT_OCR_LENGTH and text in name and not name.startswith(text)
    ]

    relation_count = sum(
        bool(matches) for matches in (custom_suffix_matches, truncated_matches, fragment_matches)
    )
    if relation_count > 1:
        related_names = {
            normalize_ship_name(name)
            for matches in (custom_suffix_matches, truncated_matches, fragment_matches)
            for name in matches
        }
        if len(related_names) != 1:
            return None, True

    if custom_suffix_matches:
        longest = max(map(len, custom_suffix_matches))
        matches = [name for name in custom_suffix_matches if len(name) == longest]
        matched_length = len(matches[0]) if len(matches) == 1 else 0
        compared_text_length = len(text) - 1
        match_type = 'custom suffix'
    elif truncated_matches:
        matches = truncated_matches
        matched_length = len(text)
        compared_text_length = len(text)
        match_type = 'truncated OCR'
    elif fragment_matches:
        matches = fragment_matches
        matched_length = len(text)
        compared_text_length = len(text)
        match_type = 'unique OCR fragment'
    else:
        return None, False

    standard_names = list(dict.fromkeys(normalize_ship_name(name) for name in matches))
    if len(standard_names) != 1:
        return None, True

    matched_candidate = matches[0]
    confidence = (
        1.0
        if match_type == 'unique OCR fragment'
        else 2 * matched_length / (compared_text_length + len(matched_candidate))
    )
    if confidence < confidence_threshold:
        return None, True
    return standard_names[0], True


def _edit_distance(a: str, b: str) -> int:
    """计算两个舰名之间的 Levenshtein 编辑距离。"""
    dp = list(range(len(b) + 1))
    for i, left in enumerate(a, start=1):
        previous, dp[0] = dp[0], i
        for j, right in enumerate(b, start=1):
            current = dp[j]
            dp[j] = min(
                dp[j] + 1,
                dp[j - 1] + 1,
                previous + (left != right),
            )
            previous = current
    return dp[-1]


def _parse_level(text: str) -> int | None:
    """从 OCR 文本中提取 ``Lv.XX`` 格式等级数字。"""
    level, _need_retry = _parse_level_with_status(text)
    return level


def parse_fleet_level(text: str) -> int | None:
    """解析准备页等级文本并限制在游戏等级范围内。"""

    def parse_digits(raw: str) -> int | None:
        normalized = normalize_level_digits(raw)
        if normalized is None:
            return None
        value = int(normalized)
        return value if is_valid_ship_level(value) else None

    for pattern in (_LEVEL_PATTERN, _LEVEL_NOISY_PATTERN, _LEVEL_SHORT_PATTERN):
        match = pattern.search(text)
        if match is not None:
            level = parse_digits(match.group(1))
            if level is not None:
                return level

    match = re.search(r'(?i)v\.?\s*([0-9liodsb]{1,3})', text)
    if match is not None:
        return parse_digits(match.group(1))

    for match in reversed(list(re.finditer(r'\d+', text))):
        value = int(match.group())
        if is_valid_ship_level(value):
            return value
        digits = match.group()
        if len(digits) >= 3 and is_valid_ship_level(int(digits[1:])):
            return int(digits[1:])
    return None


def best_fleet_level(results: list[vision.OCRItem]) -> int | None:
    """从一组等级 OCR 结果中选择可信等级。"""
    combined = ''.join(result.text.strip() for result in results)
    if re.search(r'(?i)v', combined) or _LEVEL_SHORT_PATTERN.search(combined):
        level = parse_fleet_level(combined)
        if level is not None:
            return level

    compact = re.sub(r'[.\s]', '', combined)
    if re.fullmatch(r'(?i)(?:[dsb]|[0-9liodsb]{2,3})', compact):
        normalized = normalize_level_digits(compact)
        if normalized is not None and is_valid_ship_level(int(normalized)):
            return int(normalized)

    labeled: list[tuple[float, int]] = []
    fallback: list[tuple[float, int]] = []
    for result in results:
        text = result.text.strip()
        if not text:
            continue
        level = parse_fleet_level(text)
        if level is None:
            continue
        bucket = labeled if re.search(r'(?i)v', text) else fallback
        bucket.append((result.confidence, level))
    if labeled:
        return max(labeled, key=lambda item: item[0])[1]
    if fallback:
        return max(fallback, key=lambda item: item[0])[1]
    return None


def _parse_level_with_status(text: str) -> tuple[int | None, bool]:
    """解析等级并返回是否应触发重识别。"""
    compact = text.strip().replace(' ', '')

    for pattern in (_LEVEL_PATTERN, _LEVEL_NOISY_PATTERN, _LEVEL_SHORT_PATTERN):
        match = pattern.search(compact)
        if match is None:
            continue
        raw_digits = match.group(1)
        if _noise_char_count(raw_digits) > _MAX_LEVEL_NOISE_CHARS:
            return None, True
        level = _coerce_level_digits(raw_digits)
        if level is not None:
            return level, False

    return None, False


def _noise_char_count(raw_digits: str) -> int:
    return sum(1 for ch in raw_digits if ch in LEVEL_DIGIT_CONFUSABLES)


def _coerce_level_digits(raw_digits: str) -> int | None:
    """将 OCR 提取出的数字串映射为合法等级值。"""
    digits = normalize_level_digits(raw_digits)
    if digits is None:
        return None

    # 兼容前导 0 的场景（如 051 -> 51）
    if digits.startswith('0') and len(digits) >= 3:
        value = int(digits[1:3])
        return value if is_valid_ship_level(value) else None

    # 三位以上只读取前三位；超过 110 时不再降级猜成两位等级。
    value = int(digits[:3] if len(digits) >= 3 else digits)
    return value if is_valid_ship_level(value) else None


def _parse_bare_level(text: str, confidence: float) -> int | None:
    """解析等级 ROI 中与 ``Lv.`` 标签分离的高置信度纯数字。"""
    candidate = text.removeprefix('.')
    if confidence < _MIN_SPLIT_LEVEL_CONFIDENCE:
        return None
    digits = normalize_level_digits(candidate)
    if digits is None:
        return None
    value = int(digits)
    return value if is_valid_ship_level(value) else None


def _probe_level_near_name(
    ocr: object,
    screen: np.ndarray,
    *,
    y_start: int,
    y_end: int,
    name_x: float,
    max_x: int,
) -> int | None:
    """以舰名和 DLL 行中心为锚点，顺序识别同一卡片的等级。"""
    h, w = screen.shape[:2]
    row_y = (y_start + y_end) / 2
    left, top, right, bottom = SHIP_LEVEL_CROP_OFFSETS
    x1 = max(0.0, min(float(max_x), name_x + left * w / LEGACY_WIDTH))
    x2 = max(0.0, min(float(max_x), name_x + right * w / LEGACY_WIDTH))
    y1 = max(0.0, min(float(h), row_y + top * h / LEGACY_HEIGHT))
    y2 = max(0.0, min(float(h), row_y + bottom * h / LEGACY_HEIGHT))
    if x2 <= x1 or y2 <= y1:
        return None

    source_x1 = math.floor(x1)
    source_x2 = math.ceil(x2)
    source_y1 = math.floor(y1)
    source_y2 = math.ceil(y2)
    source_crop = screen[source_y1:source_y2, source_x1:source_x2]
    if source_crop.size == 0:
        return None

    noisy_level_hits = 0

    for scale in SHIP_LEVEL_OCR_SCALES:
        enlarged_source = cv2.resize(
            source_crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        crop_x1 = round((x1 - source_x1) * scale)
        crop_x2 = round((x2 - source_x1) * scale)
        crop_y1 = round((y1 - source_y1) * scale)
        crop_y2 = round((y2 - source_y1) * scale)
        enlarged = enlarged_source[crop_y1:crop_y2, crop_x1:crop_x2]
        if enlarged.size == 0:
            continue

        prepared = enlarged

        results = _read_results(
            ocr,
            prepared,
            line=True,
            allowlist=LEVEL_OCR_ALLOWLIST,
        )
        parsed_levels: list[int] = []
        split_level_hits: list[int] = []
        for result in results:
            text = result.text.strip()
            if not text:
                continue
            split_level = _parse_bare_level(text, result.confidence)
            level, need_retry = _parse_level_with_status(text)
            if need_retry:
                noisy_level_hits += 1
                continue
            if level is not None:
                parsed_levels.append(level)
            elif split_level is not None:
                split_level_hits.append(split_level)

        parsed_levels.extend(split_level_hits)
        raw_results = [
            {
                'text': result.text,
                'confidence': result.confidence,
                'bbox': result.bbox,
            }
            for result in results
        ]
        _log.debug(
            '[选船列表] 等级OCR原始及后处理: scale={} name_x={} raw={} parsed={} noisy_hits={}',
            scale,
            name_x,
            raw_results,
            parsed_levels,
            noisy_level_hits,
        )
        if parsed_levels:
            return max(parsed_levels)

    if noisy_level_hits > _MAX_NOISY_LEVEL_HITS_BEFORE_RETRY:
        raise LevelOCRRetryNeededError(
            f'等级 OCR 噪声过高: {noisy_level_hits} 条异常等级文本 (阈值 {_MAX_NOISY_LEVEL_HITS_BEFORE_RETRY})',
        )

    return None


def read_ship_level_at_card(
    ocr: object,
    screen: np.ndarray,
    *,
    card_x: float,
    row_key: float,
) -> int | None:
    """根据已定位船卡的舰名中心和行中心识别等级。"""
    h, w = screen.shape[:2]
    row_y = round(row_key * h)
    list_w_native = int(w * LEGACY_LIST_WIDTH / LEGACY_WIDTH)
    return _probe_level_near_name(
        ocr,
        screen,
        y_start=row_y,
        y_end=row_y,
        name_x=card_x * w,
        max_x=list_w_native,
    )
