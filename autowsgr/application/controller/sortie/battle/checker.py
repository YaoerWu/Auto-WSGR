"""模块功能：读出出征页的章节事实，并在页内导航到指定章节与地图节点。

上层调用：
- application.navigation.registry：作为出征页的页内导航边动作，按入参选到目标章节。

下层依赖：
- controller.operations.sortie_page.battle_page：执行章节槽位与地图翻页的单次点击。
- navigation.types：在选章失败时抛出导航错误。
- common.system.logger：记录导航事实与失败原因。
- common.vision：按区域识别章节槽位与地图标题。

边界：拥有「选到第 X 章第 Y 节」的页内导航与落点计算；不做截图之外的设备操作、
不切标签、不做跨页面导航、不决定业务是否继续。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle.page import BattlePage
from autowsgr.application.navigation.types import NavigationError
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ROI, TextDetection, expect_ocr


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui')


# ── 数据表 ───────────────────────────────────────────────────────────────────

# 普通出征章节和地图编号到地图名称的映射。
MAP_DATABASE: dict[tuple[int, int], str] = {
    (1, 1): '母港附近海域',
    (1, 2): '东北防线海域',
    (1, 3): '仁州附近海域',
    (1, 4): '深海仁州基地',
    (1, 5): '乌兰巴托附近水域',
    (2, 1): '扶桑西部海域',
    (2, 2): '扶桑西南海域',
    (2, 3): '扶桑南部海域',
    (2, 4): '深海扶桑基地',
    (2, 5): '深海前哨核心地区',
    (2, 6): '深海前哨北方地区',
    (3, 1): '母港南部海域',
    (3, 2): '东南群岛（1）',
    (3, 3): '东南群岛（2）',
    (3, 4): '星洲海峡',
    (4, 1): '克拉代夫东部海域',
    (4, 2): '克拉代夫西部海域',
    (4, 3): '泪之扉附近海域',
    (4, 4): '泪之扉防线',
    (5, 1): '塞浦路斯附近海域',
    (5, 2): '克里特附近海域',
    (5, 3): '马耳他附近海域',
    (5, 4): '直布罗陀东部海域',
    (5, 5): '直布罗陀要塞',
    (6, 1): '洛里昂南部海域',
    (6, 2): '英吉利海峡',
    (6, 3): '斯卡帕湾',
    (6, 4): '丹麦海峡',
    (7, 1): '比斯开湾',
    (7, 2): '马德拉海域',
    (7, 3): '亚速尔海域',
    (7, 4): '百慕大三角附近海域',
    (7, 5): '百慕大三角防波堤',
    (8, 1): '百慕大中心海域',
    (8, 2): '百慕大南群岛',
    (8, 3): '北加勒比海域',
    (8, 4): '东部海岸群岛',
    (8, 5): '地峡海湾',
    (9, 1): '地峡外海',
    (9, 2): '大洋南湾',
    (9, 3): '南入海口海域',
    (9, 4): '河口外海',
    (9, 5): '南大洋群岛',
    (10, 1): '极地海峡',
}

# 每章地图数量，用于限制普通出征的地图编号范围。
CHAPTER_MAP_COUNTS: dict[int, int] = {}
for _chapter, _map_num in MAP_DATABASE:
    CHAPTER_MAP_COUNTS[_chapter] = max(CHAPTER_MAP_COUNTS.get(_chapter, 0), _map_num)
del _chapter, _map_num

# 普通出征最大章节号，由地图表推导，避免与地图数据重复维护。
TOTAL_CHAPTERS = max(CHAPTER_MAP_COUNTS)


# 章节号中文数字，用于解析侧栏槽位标签。
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


# ── 识别区域 ─────────────────────────────────────────────────────────────────

# 侧栏五个章节槽位，从上到下排列。
CHAPTER_SLOT_ROIS: tuple[ROI, ...] = (
    ROI(0.0550, 0.2650, 0.1700, 0.3550),
    ROI(0.0550, 0.3850, 0.1700, 0.4750),
    ROI(0.0550, 0.5050, 0.1700, 0.5950),
    ROI(0.0550, 0.6250, 0.1700, 0.7150),
    ROI(0.0550, 0.7450, 0.1700, 0.8350),
)

# 地图标题识别区域，读出「章号-节号 地图名」。
CHAPTER_TITLE_ROI = ROI(0.7000, 0.1800, 0.9000, 0.2150)

# 侧栏中间槽位，用作当前章节的锚点。
CHAPTER_SLOT_CENTER_INDEX = 2


# ── 导航参数 ─────────────────────────────────────────────────────────────────

# 章节与地图节点的最大尝试次数，用于限制失败循环。
CHAPTER_NAV_MAX_ATTEMPTS = 20
# 章节命中确认次数，用于避免过渡帧误判目标章节。
CHAPTER_CONFIRMATION_COUNT = 2
# 章节连续无进展上限，用于终止卡住的侧栏导航。
CHAPTER_NO_PROGRESS_LIMIT = 3
# 章节相邻切换步长与跨两章切换步长。
CHAPTER_SINGLE_STEP = 1
CHAPTER_DOUBLE_STEP = 2
# 章节或地图切换后的等待时间，用于避开页面动画过渡帧。
MAP_NAV_SETTLE_DELAY = 1.5000
# 地图标题单轮采样次数与采样间隔。稳定判据是「末两次相同」，再多的样本不参与判定。
MAP_READ_SAMPLE_COUNT = 2
MAP_READ_SAMPLE_DELAY = 0.1500
# 地图标题连续相同采样次数，用于判定当前地图稳定。
MAP_READ_STABLE_COUNT = 2
# 目标地图 OCR 命中确认次数，用于避免过渡帧误判地图节点。
MAP_CONFIRMATION_COUNT = 2
# 地图翻页连续无变化上限与识别失败上限。
MAP_MAX_STUCK = 3
MAP_NAVIGATION_MISS_LIMIT = 6
# 地图翻页额外等待时间，用于覆盖较长的节点动画。
MAP_PAGE_TRANSITION_DELAY = 0.2000


# ── 识别事实模型 ─────────────────────────────────────────────────────────────


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


# ── 页内导航入口 ─────────────────────────────────────────────────────────────


def ensure_chapter(ctx: ContextHandle, *, chapter: int, map_id: int) -> None:
    """在出征页内选到目标章节与地图节点。

    调用方负责先停在出征标签页；本函数只做页内导航：

    1. 按侧栏槽位 OCR 循环选章，连续命中两次才算到达；
    2. 按地图标题 OCR 逐跳翻页选节，卡住或识别失败达到上限时重启本轮。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        chapter: 目标章节编号，范围为 1 到 TOTAL_CHAPTERS。
        map_id: 目标地图节点编号，范围由当前章的地图数量决定。

    Raises:
        ValueError: 章节编号越界，或当前章不在已知地图数据中。
        NavigationError: 选章连续无进展或超过尝试上限。
        RuntimeError: 选节超过尝试上限，或读不到当前地图标题。
    """
    if not 1 <= chapter <= TOTAL_CHAPTERS:
        raise ValueError(f'章节编号必须为 1-{TOTAL_CHAPTERS}，收到: {chapter}')

    if not _select_target_chapter(ctx, chapter):
        raise NavigationError(f'无法导航到第 {chapter} 章')
    _select_target_map(ctx, map_id)


# ── 选章 ─────────────────────────────────────────────────────────────────────


def _select_target_chapter(ctx: ContextHandle, target: int) -> bool:
    """循环选章，到达目标章返回 True。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        target: 目标章节编号。

    Returns:
        连续确认到达目标章时为 True；连续无进展或超过尝试上限时为 False。
    """
    page = BattlePage(ctx)
    confirm_hits = 0
    previous_current: int | None = None
    no_progress = 0

    for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
        slots, current = _read_chapter_state(ctx)
        slot_state = [
            slot.chapter if slot.chapter is not None else slot.text or '---' for slot in slots
        ]
        if current is None:
            _log.warning('[UI] 章节导航：中间章节槽位识别失败（第 {} 次尝试）', attempt + 1)
            time.sleep(MAP_NAV_SETTLE_DELAY)
            continue

        if previous_current == current:
            no_progress += 1
        else:
            no_progress = 0
        previous_current = current
        if no_progress >= CHAPTER_NO_PROGRESS_LIMIT:
            _log.warning('[UI] 章节导航：连续无进展，槽位={}', slot_state)
            return False

        if current == target:
            confirm_hits += 1
            _log.info(
                '[UI] 章节导航：命中目标第 {} 章，确认 {}/{}, 槽位={}',
                target,
                confirm_hits,
                CHAPTER_CONFIRMATION_COUNT,
                slot_state,
            )
            if confirm_hits >= CHAPTER_CONFIRMATION_COUNT:
                _log.info('[UI] 章节导航：已到达第 {} 章', target)
                return True
            time.sleep(MAP_NAV_SETTLE_DELAY)
            continue

        confirm_hits = 0
        index = _calculate_chapter_slot(current, target, slots)
        if index is None:
            _log.warning(
                '[UI] 章节导航：目标第 {} 章没有可用槽位（当前={}, 槽位={}）',
                target,
                current,
                slot_state,
            )
            time.sleep(MAP_NAV_SETTLE_DELAY)
            continue

        page.click_chapter_slot(index)
        time.sleep(MAP_NAV_SETTLE_DELAY)

    _log.warning(
        '[UI] 章节导航：超过最大尝试次数（{}），目标第 {} 章',
        CHAPTER_NAV_MAX_ATTEMPTS,
        target,
    )
    return False


def _calculate_chapter_slot(
    current: int,
    target: int,
    slots: Sequence[ChapterSlot],
) -> int | None:
    """根据可见章节槽位计算下一次点击位置。

    先找视图内已经是目标章的槽位；否则按步长（相邻 1 章、跨 2 章）向目标方向移动。
    算出的槽位必须回验其识别值等于预期章号，避免按没识别出来的槽位盲点。

    Args:
        current: 当前章节编号。
        target: 目标章节编号。
        slots: 当前画面可见的章节槽位识别结果。

    Returns:
        下一次应点击的槽位索引；没有安全点击位置时返回 None。
    """
    for slot in slots:
        if slot.chapter == target:
            return slot.index

    delta = target - current
    if delta == 0:
        return None

    step = CHAPTER_DOUBLE_STEP if abs(delta) >= CHAPTER_DOUBLE_STEP else CHAPTER_SINGLE_STEP
    direction = 1 if delta > 0 else -1
    index = CHAPTER_SLOT_CENTER_INDEX + direction * step
    if not 0 <= index < len(slots):
        return None

    expected = current + direction * step
    return index if slots[index].chapter == expected else None


# ── 选节 ─────────────────────────────────────────────────────────────────────


def _select_target_map(ctx: ContextHandle, map_num: int) -> None:
    """逐跳翻页选节，到达目标节后返回。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        map_num: 目标地图节点编号。

    Raises:
        ValueError: 当前章未知，或目标节超出当前章范围。
        RuntimeError: 读不到当前地图标题，或翻页超过尝试上限。
    """
    target = int(map_num)
    info_probe = _read_map_identity(ctx)
    if info_probe is None:
        raise RuntimeError('无法识别当前地图标题，不能校验地图编号')
    current_max = CHAPTER_MAP_COUNTS.get(int(info_probe.chapter))
    if current_max is None:
        raise ValueError(f'当前章节 {info_probe.chapter} 不在已知地图数据中')
    if not 1 <= target <= current_max:
        raise ValueError(
            f'地图编号 map_num={target} 超出范围 [1, {current_max}]（当前章识别失败时请先选章）',
        )

    page = BattlePage(ctx)
    confirm = 0
    for attempt in range(CHAPTER_NAV_MAX_ATTEMPTS):
        current, stable = _read_stable_map_number(ctx)
        if current is None:
            _log.warning(
                '[UI] 地图节点导航：OCR 识别失败（第 {}/{} 次尝试）',
                attempt + 1,
                CHAPTER_NAV_MAX_ATTEMPTS,
            )
            continue

        if current == target:
            confirm += 1
            _log.info(
                '[UI] 地图节点导航：命中目标 {}-{}，确认 {}/{}',
                current,
                target,
                confirm,
                MAP_CONFIRMATION_COUNT,
            )
            if confirm >= MAP_CONFIRMATION_COUNT:
                _log.info(
                    '[UI] 地图节点导航：已到达当前章第 {} 节（地图编号 {}）',
                    target,
                    target,
                )
                return
            time.sleep(MAP_NAV_SETTLE_DELAY)
            continue

        confirm = 0
        if not stable:
            time.sleep(MAP_NAV_SETTLE_DELAY)
            continue

        _advance_map_node(ctx, page, current, target)

    raise RuntimeError(
        f'地图节点导航超过最大尝试次数 {CHAPTER_NAV_MAX_ATTEMPTS}，目标节 {target} 未到达',
    )


def _advance_map_node(
    ctx: ContextHandle,
    page: BattlePage,
    current: int,
    target: int,
) -> None:
    """按节号差逐跳翻页到目标附近。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        page: 普通出征页面单击控制器。
        current: 本轮开始时的当前节号。
        target: 目标节号。
    """
    delta = target - current
    direction = 1 if delta > 0 else -1
    remaining = abs(delta)
    stuck = 0
    misses = 0
    steps = 0

    _log.info('[UI] 地图节点导航：当前 {} -> 目标 {}（delta={:+d}）', current, target, delta)

    while remaining > 0 and stuck < MAP_MAX_STUCK and misses < MAP_NAVIGATION_MISS_LIMIT:
        if direction == 1:
            page.click_map_next()
            action = '下一节'
        else:
            page.click_map_prev()
            action = '上一节'
        steps += 1
        remaining -= 1
        _log.info('[UI] 地图节点导航：{}（剩余 {}，第 {} 跳）', action, remaining, steps)
        time.sleep(MAP_NAV_SETTLE_DELAY + MAP_PAGE_TRANSITION_DELAY)

        quick = _read_map_number(ctx)
        if quick is None:
            misses += 1
            continue
        misses = 0
        if (direction == 1 and quick <= current) or (direction == -1 and quick >= current):
            stuck = 1 if (quick == current and stuck == 0) else stuck + 1
            _log.warning(
                '[UI] 地图节点导航：翻页后仍是第{}节（cur={}, stuck={}/{}）',
                quick,
                current,
                stuck,
                MAP_MAX_STUCK,
            )
            continue
        stuck = 0
        current = quick
        remaining = abs(target - current)

    if stuck >= MAP_MAX_STUCK or misses >= MAP_NAVIGATION_MISS_LIMIT:
        _log.warning(
            '[UI] 地图节点导航：卡住或识别失败超限（stuck={}, misses={}），重启本轮',
            stuck,
            misses,
        )


def _read_stable_map_number(ctx: ContextHandle) -> tuple[int | None, bool]:
    """多次采样读取当前地图编号，并判断采样是否稳定。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。

    Returns:
        当前地图编号与稳定标记；一次都没读到时为 (None, False)。
    """
    map_numbers: list[int] = []
    for sample_index in range(MAP_READ_SAMPLE_COUNT):
        number = _read_map_number(ctx)
        if number is not None:
            map_numbers.append(number)
        if sample_index < MAP_READ_SAMPLE_COUNT - 1:
            time.sleep(MAP_READ_SAMPLE_DELAY)
    return _judge_stable_map_number(map_numbers)


def _read_map_number(ctx: ContextHandle) -> int | None:
    """读一次当前地图节点编号。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。

    Returns:
        当前节点编号；标题读不到或无法解析时为 None。
    """
    identity = _read_map_identity(ctx)
    return identity.map_num if identity is not None else None


def _judge_stable_map_number(map_numbers: Sequence[int]) -> tuple[int | None, bool]:
    """判断多次采样的地图编号是否稳定。

    末两次相同即为稳定；否则取众数并标记为抖动。

    Args:
        map_numbers: 本轮采样到的地图编号。

    Returns:
        当前地图编号与稳定标记；没有采样结果时为 (None, False)。
    """
    if not map_numbers:
        return None, False
    if len(map_numbers) >= MAP_READ_STABLE_COUNT and map_numbers[-1] == map_numbers[-2]:
        return map_numbers[-1], True

    candidate = max(set(map_numbers), key=map_numbers.count)
    _log.warning('[UI] 地图节点导航：OCR 抖动 {}，本轮不点击', map_numbers)
    return candidate, False


# ── 章节与地图识别 ───────────────────────────────────────────────────────────


def _read_chapter_state(ctx: ContextHandle) -> tuple[tuple[ChapterSlot, ...], int | None]:
    """用一帧截图读出侧栏槽位和当前章节。

    槽位与标题必须在同一帧读取：章节切换动画期间两帧的章号可能不一致。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。

    Returns:
        按页面顺序排列的章节槽位，以及确认到的当前章节编号；无法确认时为 None。
    """
    result = expect_ocr(
        ctx,
        roi=(*CHAPTER_SLOT_ROIS, CHAPTER_TITLE_ROI),
        recognition_profile='single_line',
        attempts=1,
    )
    groups = result.observation
    slots = tuple(
        ChapterSlot(
            index=index,
            chapter=_parse_chapter_label(text),
            text=text.strip(),
            confidence=confidence,
        )
        for index, (text, confidence) in enumerate(
            _read_best_text(group) for group in groups[: len(CHAPTER_SLOT_ROIS)]
        )
    )
    title = _parse_map_title(_read_longest_text(groups[len(CHAPTER_SLOT_ROIS)]))

    current = slots[CHAPTER_SLOT_CENTER_INDEX].chapter
    if current is None and title is not None:
        current = title.chapter
    if current is not None and title is not None and title.chapter != current:
        _log.warning('[UI] 章节状态不一致：侧栏第{}章，标题第{}章', current, title.chapter)
    _log.debug(
        '[UI] 章节槽位：{}',
        [(slot.index, slot.chapter, slot.text, round(slot.confidence, 2)) for slot in slots],
    )
    return slots, current


def _read_map_identity(ctx: ContextHandle) -> MapIdentity | None:
    """从一帧截图的地图标题读出章节、关卡和名称。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。

    Returns:
        当前地图的结构化标识；标题为空或无法解析时为 None。
    """
    result = expect_ocr(ctx, roi=CHAPTER_TITLE_ROI, attempts=1)
    text = _read_longest_text(result.observation)
    if not text:
        _log.debug('[UI] 地图标题 OCR 无结果')
        return None

    info = _parse_map_title(text)
    if info is None:
        _log.debug("[UI] 地图标题解析失败：'{}'", text)
    return info


def _read_best_text(detections: Sequence[TextDetection]) -> tuple[str, float]:
    """从一组识别结果里取出第一个能解析成章节号的文本。

    Args:
        detections: 同一识别区域内按阅读顺序排列的检测结果。

    Returns:
        文本与置信度；都解析不出章节号时退回置信度最高的一条，没有结果时为空串。
    """
    if not detections:
        return '', 0.0
    for detection in detections:
        if _parse_chapter_label(detection.recognized_text) is not None:
            return detection.recognized_text, detection.confidence_score
    best = max(detections, key=lambda detection: detection.confidence_score)
    return best.recognized_text, best.confidence_score


def _read_longest_text(detections: Sequence[TextDetection]) -> str:
    """从一组识别结果里取出文本最长的一条。

    Args:
        detections: 同一识别区域内按阅读顺序排列的检测结果。

    Returns:
        最长的识别文本；没有结果时为空串。
    """
    if not detections:
        return ''
    return max((detection.recognized_text for detection in detections), key=len)


def _parse_chapter_label(text: str) -> int | None:
    """解析侧栏章节标签。

    Args:
        text: 章节标签 OCR 文本。

    Returns:
        章节编号；文本格式不符合征战页章节规则时为 None。
    """
    compact = re.sub(r'\s+', '', text)
    if not compact or re.fullmatch(r'[-—_~]+', compact):
        return None

    match = re.fullmatch(r'第?([0-9]{1,2}|[一二三四五六七八九十百]+)章', compact)
    if match is None:
        return None

    token = match.group(1)
    chapter = int(token) if token.isdigit() else _CHAPTER_NUMERALS.get(token)
    if chapter is None or not 1 <= chapter <= TOTAL_CHAPTERS:
        return None
    return chapter


def _parse_map_title(text: str) -> MapIdentity | None:
    """解析地图标题文本，并修正 OCR 粘连的关卡数字。

    Args:
        text: 地图标题 OCR 文本。

    Returns:
        结构化地图标识；无法解析章节和地图编号时为 None。
    """
    match = re.search(r'(\d{1,2})\s*[--—]\s*(\d)\s*[/]?\s*(.*)', text)
    if match:
        chapter = int(match.group(1))
        map_num = int(match.group(2))
        name = match.group(3).strip()
        cleaned_name = re.sub(r'^\d+', '', name).strip()

        db_name = MAP_DATABASE.get((chapter, map_num))
        if db_name is not None:
            name = db_name
        elif cleaned_name != name:
            _log.debug("[UI] OCR 名称残留数字：'{}' → '{}'", name, cleaned_name)
            name = cleaned_name
        return MapIdentity(chapter, map_num, name, text)

    match = re.search(r'(\d+)\s*[--—]\s*(\d+)\s*[/]?\s*(.*)', text)
    if not match:
        return None

    raw_chapter = int(match.group(1))
    raw_map_num = int(match.group(2))
    raw_name = match.group(3).strip()
    if raw_map_num >= 10 and 1 <= raw_chapter <= TOTAL_CHAPTERS:
        candidate = int(str(raw_map_num)[0])
        db_name = MAP_DATABASE.get((raw_chapter, candidate))
        if db_name is not None:
            _log.debug(
                "[UI] OCR 校正：'{}'→{}-{} '{}' (数据库: '{}')",
                text,
                raw_chapter,
                candidate,
                raw_name,
                db_name,
            )
            return MapIdentity(raw_chapter, candidate, db_name, text)

    return MapIdentity(raw_chapter, raw_map_num, raw_name, text)


__all__ = ['ensure_chapter']
