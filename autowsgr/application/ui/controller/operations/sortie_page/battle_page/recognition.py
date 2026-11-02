"""模块功能：识别地图标题 OCR 文本并解析为地图标识。

上层调用：
- application.ui.controller.operations.sortie_page.battle_page.page：在普通出征导航中读取章节和地图状态。
- business.combat.bettle、application.runtime.context：读取普通出征统计。
- testing.ui、tools：验证地图标题解析和 OCR 结果。

下层依赖：
- application.ui.controller.operations.sortie_page.battle_page.constants：提供地图数据和识别校准。
- common.vision：执行 OCR 区域裁剪和文本识别。

本模块只负责普通出征页面的图像/像素识别、OCR 输入、文本解析和识别结果模型；识别入口
保持为内部函数，不通过 battle_page 包入口导出。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2

from autowsgr.application.ui.controller.operations.sortie_page.battle_page import constants
from autowsgr.application.vision.sortie_recognition import (
    LootShipCount,
    recognize_loot_count,
    recognize_ship_count,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.common.vision import OCREngine


_log = get_logger('ui')


# ── 普通出征识别参数 ──────────────────────────────────────────────────────────

CHAPTER_OCR_ALLOWLIST = '0123456789第章一二三四五六七八九十'  # 章节标签 OCR 允许字符。
MAP_READ_SAMPLE_COUNT = 3  # 地图标题单轮 OCR 采样次数，用于确认页面动画已经结束。
MAP_READ_SAMPLE_DELAY = 0.1500  # 地图标题 OCR 采样间隔，用于观察标题是否稳定。
MAP_READ_STABLE_COUNT = 2  # 地图标题连续相同采样次数，用于判定当前地图稳定。
MAP_CONFIRMATION_COUNT = 2  # 目标地图 OCR 命中确认次数，用于避免过渡帧误判地图节点。
SIDEBAR_SCAN_STEP = 0.0100  # 高亮扫描步长，用于平衡定位精度和截图采样量。
SIDEBAR_BRIGHTNESS_RATIO = 0.7000  # 高亮自适应比例，用于适配不同截图亮度。
SIDEBAR_BRIGHTNESS_OFFSET = 40  # 高亮自适应偏移，用于区分亮度段和侧栏背景。
SIDEBAR_MIN_SEGMENT_STEPS = 2  # 高亮有效段最小采样数，用于过滤孤立亮点。
SIDEBAR_COVERAGE_MIN = 0.0300  # 高亮段最小覆盖率，用于排除过短误识别。
SIDEBAR_COVERAGE_MAX = 0.6000  # 高亮段最大覆盖率，用于排除大面积背景误识别。
SIDEBAR_CONTINUITY_FACTOR = 1.5000  # 高亮段连续性倍数，用于判断相邻采样是否属于同一段。


_CHAPTER_NUMERALS: dict[str, int] = {
    '一': 1,
    '二': 2,
    '三': 3,
    '四': 4,
    '五': 5,
    '六': 6,
    '七': 7,
    '八': 8,
    '九': 9,
    '十': 10,
}


@dataclass(frozen=True, slots=True)
class MapIdentity:
    """地图标题解析后的章节、关卡和名称。"""

    chapter: int
    map_num: int
    name: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class ChapterSlot:
    """一个固定章节槽位的 OCR 结果和页面索引。"""

    index: int
    chapter: int | None
    text: str
    confidence: float


# ── 章节标签识别 ──────────────────────────────────────────────────────────────


def _parse_chapter_label(text: str) -> int | None:
    """解析侧栏章节标签，无法确认时返回 ``None``。

    Args:
        text: 章节标签 OCR 文本。

    Returns:
        章节编号；文本格式不符合普通出征章节规则时返回 ``None``。
    """
    compact = re.sub(r'\s+', '', text)
    if not compact or re.fullmatch(r'[-—_~]+', compact):
        return None

    match = re.fullmatch(r'第?([0-9]{1,2}|[一二三四五六七八九十百]+)章', compact)
    if match is None:
        return None

    token = match.group(1)
    chapter = int(token) if token.isdigit() else _CHAPTER_NUMERALS.get(token)
    if chapter is None or not 1 <= chapter <= constants.TOTAL_CHAPTERS:
        return None
    return chapter


def _recognize_chapter_slots(
    screen: np.ndarray,
    ocr: OCREngine,
) -> tuple[ChapterSlot, ...]:
    """从固定侧栏槽位读取章节标签，并在必要时使用二值图复识别。

    Args:
        screen: 普通出征地图页面的 RGB 截图。
        ocr: 调用方注入的 OCR 引擎。

    Returns:
        按页面顺序排列的章节槽位识别结果。
    """
    slots: list[ChapterSlot] = []
    for index, roi in enumerate(constants.CHAPTER_SLOT_ROIS):
        crop = PixelChecker.crop(screen, *roi)
        result = ocr.recognize_single(crop, allowlist=CHAPTER_OCR_ALLOWLIST)
        chapter = _parse_chapter_label(result.text)

        if chapter is None and result.text.strip() not in {'', '---'}:
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
            _, binary = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
            binary_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            binary_result = ocr.recognize_single(
                binary_rgb,
                allowlist=CHAPTER_OCR_ALLOWLIST,
            )
            binary_chapter = _parse_chapter_label(binary_result.text)
            if binary_chapter is not None:
                result = binary_result
                chapter = binary_chapter

        slots.append(
            ChapterSlot(
                index=index,
                chapter=chapter,
                text=result.text.strip(),
                confidence=result.confidence,
            ),
        )

    _log.debug(
        '[UI] 章节槽位: {}',
        [(slot.index, slot.chapter, slot.text, round(slot.confidence, 2)) for slot in slots],
    )
    return tuple(slots)


# ── 地图标题识别 ──────────────────────────────────────────────────────────────


def _parse_map_title(text: str) -> MapIdentity | None:
    """解析地图标题文本，并修正 OCR 粘连的关卡数字。

    Args:
        text: 地图标题 OCR 文本。

    Returns:
        结构化地图标识；无法解析章节和地图编号时返回 ``None``。
    """
    match = re.search(r'(\d{1,2})\s*[--—]\s*(\d)\s*[/]?\s*(.*)', text)
    if match:
        chapter = int(match.group(1))
        map_num = int(match.group(2))
        name = match.group(3).strip()
        cleaned_name = re.sub(r'^\d+', '', name).strip()

        db_name = constants.MAP_DATABASE.get((chapter, map_num))
        if db_name is not None:
            name = db_name
        elif cleaned_name != name:
            _log.debug(
                "[UI] OCR 名称残留数字: '{}' → '{}'",
                name,
                cleaned_name,
            )
            name = cleaned_name
        return MapIdentity(chapter, map_num, name, text)

    match = re.search(r'(\d+)\s*[--—]\s*(\d+)\s*[/]?\s*(.*)', text)
    if not match:
        return None

    raw_chapter = int(match.group(1))
    raw_map_num = int(match.group(2))
    raw_name = match.group(3).strip()
    if raw_map_num >= 10 and 1 <= raw_chapter <= constants.TOTAL_CHAPTERS:
        candidate = int(str(raw_map_num)[0])
        db_name = constants.MAP_DATABASE.get((raw_chapter, candidate))
        if db_name is not None:
            _log.debug(
                "[UI] OCR 校正: '{}'→{}-{} '{}' (数据库: '{}')",
                text,
                raw_chapter,
                candidate,
                raw_name,
                db_name,
            )
            return MapIdentity(raw_chapter, candidate, db_name, text)

    return MapIdentity(raw_chapter, raw_map_num, raw_name, text)


def _recognize_map(screen: np.ndarray, ocr: OCREngine) -> MapIdentity | None:
    """从地图页面截图中识别当前地图标题。

    Args:
        screen: 普通出征地图页面的 RGB 截图。
        ocr: 调用方注入的 OCR 引擎。

    Returns:
        当前地图的结构化标识；标题为空或无法解析时返回 ``None``。
    """
    x1, y1, x2, y2 = constants.TITLE_CROP_REGION
    cropped = PixelChecker.crop(screen, x1, y1, x2, y2)
    result = ocr.recognize_maxlen(cropped)
    if not result.text:
        _log.debug('[UI] 地图标题 OCR 无结果')
        return None

    info = _parse_map_title(result.text)
    if info is None:
        _log.debug("[UI] 地图标题解析失败: '{}'", result.text)
    else:
        _log.debug(
            '[UI] 地图识别: 第{}章 {}-{} {}',
            info.chapter,
            info.chapter,
            info.map_num,
            info.name,
        )
    return info


# ── 当前章节高亮识别 ──────────────────────────────────────────────────────────


def _read_selected_chapter_y(screen: np.ndarray) -> float | None:  # noqa: PLR0912
    """从普通出征侧栏高亮中识别当前章节的点击纵坐标。

    Args:
        screen: 普通出征地图页面的 RGB 截图。

    Returns:
        高亮章节的归一化纵坐标；无法确认有效高亮段时返回 ``None``。
    """
    scan_start, scan_end = constants.SIDEBAR_SCAN_REGION
    scan_x = scan_start[0]
    y_min = scan_start[1]
    y_max = scan_end[1]
    step = SIDEBAR_SCAN_STEP

    ys: list[float] = []
    brights: list[int] = []
    max_bright = 0
    sum_bright = 0

    y = y_min
    while y <= y_max:
        color = PixelChecker.get_pixel(screen, scan_x, y)
        brightness = color.r + color.g + color.b
        ys.append(y)
        brights.append(brightness)
        max_bright = max(max_bright, brightness)
        sum_bright += brightness
        y += step

    total_count = len(ys)
    if total_count == 0:
        _log.warning('[UI] 侧边栏扫描采样为空')
        return None

    avg_bright = sum_bright / total_count
    adaptive_threshold = max(
        int(max_bright * SIDEBAR_BRIGHTNESS_RATIO),
        int(avg_bright) + SIDEBAR_BRIGHTNESS_OFFSET,
    )
    segments: list[list[tuple[float, int]]] = []
    current: list[tuple[float, int]] = []
    prev_y: float | None = None

    for y, brightness in zip(ys, brights, strict=True):
        if brightness >= adaptive_threshold:
            if prev_y is not None and y - prev_y <= step * SIDEBAR_CONTINUITY_FACTOR:
                current.append((y, brightness))
            else:
                if current:
                    segments.append(current)
                current = [(y, brightness)]
            prev_y = y
        else:
            if current:
                segments.append(current)
                current = []
            prev_y = None
    if current:
        segments.append(current)

    valid = [segment for segment in segments if len(segment) >= SIDEBAR_MIN_SEGMENT_STEPS]
    segment_info = sorted(
        (
            len(segment),
            min(item[0] for item in segment),
            max(item[0] for item in segment),
        )
        for segment in segments
    )[::-1][:3]
    if not valid:
        _log.debug(
            '[UI] 侧边栏无有效高亮段 (segs={}, 最长段={}, max_br={} avg_br={} th={})',
            len(segments),
            segment_info[0] if segment_info else 'none',
            max_bright,
            int(avg_bright),
            adaptive_threshold,
        )
        return None

    longest = max(valid, key=len)
    cover = len(longest) / total_count
    if not SIDEBAR_COVERAGE_MIN <= cover <= SIDEBAR_COVERAGE_MAX:
        _log.debug(
            '[UI] 侧边栏高亮段覆盖异常 cover={:.0%} (segs={} valid={}), 放弃',
            cover,
            len(segments),
            len(valid),
        )
        return None

    total_w = sum(item[1] for item in longest)
    if total_w <= 0:
        return None
    center = sum(item[0] * item[1] for item in longest) / total_w
    _log.debug(
        '[UI] 侧边栏选中章 y={:.3f} (段长{}点 {:.3f}-{:.3f}, max_br={} avg_br={} th={} cover={:.0%})',
        center,
        len(longest),
        longest[0][0],
        longest[-1][0],
        max_bright,
        int(avg_bright),
        adaptive_threshold,
        cover,
    )
    return center


# ── 识别入口 ─────────────────────────────────────────────────────────────────


def _read_chapter_slots(
    screen: np.ndarray,
    ocr: OCREngine | None,
) -> tuple[ChapterSlot, ...]:
    """读取普通出征侧栏的固定章节槽位。

    Args:
        screen: 普通出征地图页面的 RGB 截图。
        ocr: 调用方注入的 OCR 引擎，可为 ``None``。

    Returns:
        按页面顺序排列的章节槽位识别结果。

    Raises:
        RuntimeError: OCR 引擎未注入。
    """
    if ocr is None:
        raise RuntimeError('需要 OCR 引擎才能读取章节槽位')
    return _recognize_chapter_slots(screen, ocr)


def _read_map(screen: np.ndarray, ocr: OCREngine | None) -> MapIdentity | None:
    """读取普通出征地图标题并解析为地图信息。

    Args:
        screen: 普通出征地图页面的 RGB 截图。
        ocr: 调用方注入的 OCR 引擎，可为 ``None``。

    Returns:
        当前地图的结构化标识；无法识别或解析时返回 ``None``。

    Raises:
        RuntimeError: OCR 引擎未注入。
    """
    if ocr is None:
        raise RuntimeError('需要 OCR 引擎才能读取地图标题')
    return _recognize_map(screen, ocr)


# ── 出征结果识别 ──────────────────────────────────────────────────────────────


def _read_loot_and_ship_count(
    screen: np.ndarray,
    ocr: OCREngine | None,
    *,
    read_loot: bool = True,
) -> LootShipCount:
    """读取普通出征页面的战利品和舰船数量。

    Args:
        screen: 普通出征页面的 RGB 截图。
        ocr: 调用方注入的 OCR 引擎，可为 ``None``。
        read_loot: 是否同时读取战利品数量。

    Returns:
        读取到的战利品和舰船数量，未识别的项目为 ``None``。

    Raises:
        RuntimeError: OCR 引擎未注入。
    """
    if ocr is None:
        raise RuntimeError('需要 OCR 引擎才能读取掉落数量')
    loot = recognize_loot_count(screen, ocr) if read_loot else None
    ship = recognize_ship_count(screen, ocr)
    return LootShipCount(loot=loot, ship=ship)
