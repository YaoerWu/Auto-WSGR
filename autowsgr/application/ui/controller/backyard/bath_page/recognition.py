"""模块功能：读取浴室页面、修理浮层和修理卡片的截图事实。

上层调用：
- application.ui.controller.backyard.bath_page.page：读取页面状态和修理卡片事实。

下层依赖：
- application.ui.controller.backyard.bath_page.constants：提供页面坐标和按钮颜色校准参数。
- common.constants、common.vision 和 cv2：提供词表、视觉识别和图像处理能力。

边界：
本模块只接收截图和显式 OCR 引擎，不创建上下文、不操作设备、不编排修理流程。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2

from autowsgr.application.fleet_select.rules.shipnames import SHIPNAMES
from autowsgr.application.navigation.types import PageMatch, PageName
from autowsgr.application.ui.controller.backyard.bath_page import constants
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker, PixelChecker
from autowsgr.common.vision.adapters.pixel_matching import Color


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.common.vision.ocr import OCREngine

_log = get_logger('ui.bath_page.recognition')

# ── 页面状态识别参数 ─────────────────────────────────────────────────────────

_TIME_PATTERN = re.compile(r'\d{2}:\d{2}:\d{2}')
"""修理时间格式：HH:MM:SS。"""

_SHIP_NAME_MATCH_THRESHOLD = 3  # 舰船名称允许的最大编辑距离。
_BORDER_THRESHOLD = 220  # 明亮卡片边框的灰度二值化阈值（像素灰度值）。
_CARD_WIDTH_RANGE = (150, 250)  # 候选卡片矩形的允许宽度范围（像素）。
_CARD_HEIGHT_RANGE = (400, 600)  # 候选卡片矩形的允许高度范围（像素）。
_FULL_CARD_WIDTH = 174  # 完整舰船卡片的参考宽度（像素）。
_FULL_CARD_WIDTH_RATIO = 0.9  # 实际宽度达到参考宽度的比例才算完整。
_EDGE_MARGIN = 5  # 卡片距离截图左右边缘的最小距离（像素）。
_NAME_Y_RANGE = (118, 150)  # 卡片下半部分中舰船名称的 y 坐标范围（像素）。
_TIME_CROP_Y = 195  # 从卡片下半部分第几行（像素）开始裁剪修理时间。
_TIME_SCALE = 2  # 修理时间 OCR 前的图像放大倍数。


@dataclass(frozen=True, slots=True)
class RepairShipInfo:
    """选择修理浮层中识别到的舰船信息。

    Attributes:
        name: 舰船中文名称。
        position: 舰船卡片中心的相对点击坐标。
        repair_time: OCR 得到的修理时长文本，例如 ``"01:23:45"``；未识别时为空。
    """

    name: str
    position: tuple[float, float]
    repair_time: str = ''


def convert_repair_time_to_seconds(time_str: str) -> int:
    """将 OCR 得到的 ``HH:MM:SS`` 修理时长转换为秒数。

    Args:
        time_str: 修理时长文本；空值、字段数量不正确或非数字字段均视为解析失败。

    Returns:
        修理总秒数；解析失败返回 ``0``。
    """
    if not time_str:
        return 0
    parts = time_str.split(':')
    if len(parts) != 3:
        return 0
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return 0


# ── 页面和浮层事实 ───────────────────────────────────────────────────────────


def check_current_page(screen: np.ndarray) -> PageMatch:
    """判断截图是否属于浴室页面，包括选择修理浮层状态。

    Args:
        screen: 浴室页面 RGB 截图。

    Returns:
        页面匹配结果；基础页面或选择修理浮层命中时均视为浴室页面。
    """
    name = PageName.BATH.value
    result = ImageChecker.find_template(screen, Templates.Bath.BATH, confidence=0.85)
    if result is not None:
        return PageMatch(name=name, matched=True, score=result.confidence)

    overlay = ImageChecker.find_template(screen, Templates.Bath.CHOOSE_REPAIR, confidence=0.85)
    if overlay is not None:
        return PageMatch(name=name, matched=True, score=overlay.confidence)
    return PageMatch(name=name, matched=False, score=0.0)


def check_choose_repair_overlay(screen: np.ndarray) -> bool:
    """检查选择修理浮层是否处于打开状态。

    Args:
        screen: 当前页面 RGB 截图。

    Returns:
        浮层模板命中时返回 True，否则返回 False。
    """
    return ImageChecker.template_exists(screen, Templates.Bath.CHOOSE_REPAIR, confidence=0.85)


def check_repair_all_available(screen: np.ndarray) -> bool:
    """检查选择修理浮层的全部修理按钮是否可点击。

    Args:
        screen: 当前选择修理浮层 RGB 截图。

    Returns:
        按钮颜色符合校准值时返回 True，否则返回 False。
    """
    color, tolerance = constants.REPAIR_ALL_BUTTON_COLOR
    pixel = PixelChecker.get_pixel(screen, *constants.CLICK_REPAIR_ALL)
    return pixel.near(Color.from_rgb_tuple(color), tolerance)


def check_close_overlay_available(screen: np.ndarray) -> bool:
    """检查选择修理浮层的关闭按钮是否可见。

    Args:
        screen: 当前选择修理浮层 RGB 截图。

    Returns:
        关闭按钮颜色符合校准值时返回 True，否则返回 False。
    """
    color, tolerance = constants.CLOSE_OVERLAY_BUTTON_COLOR
    pixel = PixelChecker.get_pixel(screen, *constants.CLICK_CLOSE_OVERLAY)
    return pixel.near(Color.from_rgb_tuple(color), tolerance)


# ── 修理卡片事实 ────────────────────────────────────────────────────────────


def recognize_repair_cards(
    screen: np.ndarray,
    ocr: OCREngine,
) -> list[RepairShipInfo]:
    """从选择修理浮层截图中识别所有完整可见的舰船卡片。

    Args:
        screen: RGB 截图，形状为 ``(H, W, 3)``。
        ocr: OCR 引擎实例。

    Returns:
        按从左到右排列的舰船信息列表，仅包含完整可见且至少识别出名称或
        修理时长的卡片。
    """
    w = screen.shape[1]
    # 轮廓检测使用转换后的 BGR 图像，卡片 OCR 仍读取原始 RGB 截图。
    bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)
    cards = _detect_card_rects(bgr)

    _log.debug('[UI] 修理识别 → 检测卡片：数量={}', len(cards))

    result: list[RepairShipInfo] = []
    for x, y, cw, ch in cards:
        if not _is_fully_visible(x, cw, w):
            _log.debug(
                '[UI] 修理识别 → 跳过卡片：横坐标={}，宽度={}，原因={!r}',
                x,
                cw,
                '卡片不完整',
            )
            continue

        card_img = screen[y : y + ch, x : x + cw]
        try:
            info = _ocr_card(card_img, ocr, x, cw, w)
        except Exception:
            _log.opt(exception=True).warning(
                '[UI] 修理识别 → 识别失败：横坐标={}，宽度={}，结果=跳过',
                x,
                cw,
            )
            continue

        if info is not None:
            result.append(info)
            _log.debug(
                '[UI] 修理识别 → 卡片：舰船={!r}，修理时间={!r}',
                info.name,
                info.repair_time,
            )

    _log.debug('[UI] 修理识别 → 汇总：有效数量={}，检测数量={}', len(result), len(cards))
    return result


def _is_fully_visible(
    x: int,
    w: int,
    img_width: int,
    *,
    min_width: int = _FULL_CARD_WIDTH,
    width_ratio: float = _FULL_CARD_WIDTH_RATIO,
    edge_margin: int = _EDGE_MARGIN,
) -> bool:
    """判断卡片是否完整可见，避免页面点击或 OCR 使用截断卡片。

    Args:
        x: 卡片左边缘 x 坐标。
        w: 卡片宽度。
        img_width: 图片总宽度。
        min_width: 标准完整卡片宽度参考值。
        width_ratio: 宽度低于 ``min_width * width_ratio`` 时视为截断。
        edge_margin: 卡片距离图片左右边缘的最小像素距离。

    Returns:
        卡片未被边缘截断且宽度达到阈值时为 ``True``，否则为 ``False``。
    """
    if x < edge_margin:
        return False
    if x + w > img_width - edge_margin:
        return False
    return w >= min_width * width_ratio


def _detect_card_rects(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """从截图中检测满足几何阈值的卡片矩形。

    Args:
        image: 用于轮廓检测的截图。

    Returns:
        按 x 坐标排序的 ``(x, y, w, h)`` 列表；未检测到卡片时返回空列表。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, _BORDER_THRESHOLD, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    cards: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if (
            _CARD_WIDTH_RANGE[0] < w < _CARD_WIDTH_RANGE[1]
            and _CARD_HEIGHT_RANGE[0] < h < _CARD_HEIGHT_RANGE[1]
        ):
            cards.append((x, y, w, h))

    cards.sort(key=lambda r: r[0])
    return cards


def _normalize_time(raw: str) -> str:
    """把 OCR 原始时间文本统一为可解析的 ``HH:MM:SS`` 形式。

    OCR 引擎常将 ``:`` 识别为 ``;`` 、 ``,`` 或 ``.``，需统一替换。

    Args:
        raw: OCR 原始文本，可能包含“耗时”前缀、空格或错误分隔符。

    Returns:
        规范化后的时间文本；无法恢复完整格式时返回过滤后的文本。
    """
    t = raw.replace('耗时', '').replace(' ', '')
    t = t.replace(';', ':').replace(',', ':').replace('.', ':')
    t = t.strip(':')
    # 只保留时间字段允许的字符。
    t = ''.join(c for c in t if c.isdigit() or c == ':')
    # 连续分隔符不代表有效时间，先压缩为一个。
    while '::' in t:
        t = t.replace('::', ':')
    m = _TIME_PATTERN.search(t)
    if m:
        return m.group(0)
    # OCR 丢失分隔符时，按六位数字恢复 HH:MM:SS。
    digits = ''.join(c for c in t if c.isdigit())
    if len(digits) == 6:
        return f'{digits[0:2]}:{digits[2:4]}:{digits[4:6]}'
    return t


def _ocr_card(
    card_img: np.ndarray,
    ocr: OCREngine,
    card_x: float,
    card_w: float,
    img_width: int,
) -> RepairShipInfo | None:
    """识别单张完整卡片的舰船名称、修理时长和点击位置。

    Args:
        card_img: 卡片区域图像（RGB）。
        ocr: OCR 引擎实例。
        card_x: 卡片在原图中的 x 坐标，用于计算点击位置。
        card_w: 卡片宽度。
        img_width: 原图宽度。

    Returns:
        识别到的舰船信息；名称和修理时长均未识别时返回 ``None``。
    """
    ch = card_img.shape[0]
    half_y = ch // 2
    bottom = card_img[half_y:, :]

    # ── 舰船名称 ─────────────────────────────────────────────────────────────
    name_start, name_end = _NAME_Y_RANGE
    name = ocr.recognize_ship_name(
        bottom[name_start:name_end, :],
        candidates=SHIPNAMES,
        threshold=_SHIP_NAME_MATCH_THRESHOLD,
    )

    # ── 修理时长 ─────────────────────────────────────────────────────────────
    time_roi = bottom[_TIME_CROP_Y:, :]
    trh, trw = time_roi.shape[:2]
    scaled = cv2.resize(
        time_roi,
        (trw * _TIME_SCALE, trh * _TIME_SCALE),
        interpolation=cv2.INTER_CUBIC,
    )
    time_results = ocr.recognize(scaled)

    time_text: str = ''
    for r in time_results:
        if r.bbox is None:
            continue
        txt = r.text
        if '耗时' in txt or ':' in txt or ';' in txt or '.' in txt:
            normalized = _normalize_time(txt)
            if _TIME_PATTERN.match(normalized):
                time_text = normalized
                break

    if name is None and time_text == '':
        return None

    # 返回卡片中心的相对坐标，供页面控制器点击整张卡片。
    rel_x = (card_x + card_w / 2) / img_width
    rel_y = 0.5  # 点击卡片中心

    return RepairShipInfo(
        name=name or '',
        position=(rel_x, rel_y),
        repair_time=time_text,
    )
