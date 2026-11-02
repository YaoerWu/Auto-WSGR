"""模块功能：执行决战总览、地图节点和战备舰队的 OCR 识别。

上层调用：
- application.ui.controller.operations.sortie_page.decisive_page.page：读取当前章节编号。
- application.ui.controller.operations.sortie_page.decisive_page.map_page：读取节点和战备舰队结果。
- business.combat.decisive：消费章节、节点、舰船和技能识别结果。

下层依赖：
- application.ui.controller.operations.sortie_page.decisive_page.constants：提供 OCR 裁剪区域。
- common.vision：提供 OCR 引擎、ROI 裁剪和地图识别接口。

本模块只负责截图数据的文字识别和解析，不点击设备、不等待页面，也不决定业务策略。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import cv2

from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    CHAPTER_NUM_AREA,
    COST_AREA,
    FLEET_CARD_CLICK_Y,
    FLEET_CARD_X_POSITIONS,
    NODE_CROP_OFFSET,
    RESOURCE_AREA,
    SHIP_NAME_X_RANGES,
    SHIP_NAME_Y_RANGE,
    SKILL_SHIP_AREA,
)
from autowsgr.application.vision.combat_recognition import recognize_ship_drop
from autowsgr.application.vision.ship_list import recognize_ships_in_list
from autowsgr.business.combat.types import FleetSelection
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ROI, OCREngine, PixelChecker


if TYPE_CHECKING:
    import numpy as np

    from autowsgr.application.vision.combat_recognition import ShipDropResult
    from autowsgr.application.vision.native import ApiDll


_log = get_logger('ui.decisive')


def read_chapter_number(
    ocr: OCREngine | None,
    screen: np.ndarray,
) -> int | None:
    """从决战总览页 OCR 读取当前章节编号。

    Args:
        ocr: 调用方注入的 OCR 引擎；未提供时返回 ``None``。
        screen: RGB 截图，形状为 ``(H, W, 3)``。

    Returns:
        识别出的章节编号；OCR 无结果或无法解析时返回 ``None``。
    """
    if ocr is None:
        return None

    cropped = PixelChecker.crop(screen, *CHAPTER_NUM_AREA)
    result = ocr.recognize_single(cropped, allowlist='0123456789Ex-')
    if not result.text:
        _log.debug('[决战 OCR] 章节编号没有识别结果')
        return None

    match = re.search(r'(\d)', result.text[::-1])
    if match is None:
        _log.debug("[决战 OCR] 章节编号解析失败: '{}'", result.text)
        return None

    chapter = int(match.group(1))
    _log.debug("[决战 OCR] 章节编号: '{}' -> Ex-{}", result.text, chapter)
    return chapter


def recognize_fleet_options(
    ocr: OCREngine,
    screen: np.ndarray,
    fallback_score: int | None = None,
) -> tuple[int, dict[str, FleetSelection]]:
    """OCR 读取战备舰队获取浮层中的可购买选项。

    Args:
        ocr: 调用方注入的 OCR 引擎。
        screen: 战备舰队获取浮层的 RGB 截图。
        fallback_score: 分数 OCR 失败时使用的上一轮分数。

    Returns:
        ``(score, selections)``，分别表示可用分数和可购买舰船选项。
    """
    _log.debug('[舰队 OCR] 开始识别战备舰队可选项')

    resource_roi = ROI(
        x1=RESOURCE_AREA[0][0],
        y1=RESOURCE_AREA[1][1],
        x2=RESOURCE_AREA[1][0],
        y2=RESOURCE_AREA[0][1],
    )
    score_image = _prepare_text_roi(resource_roi.crop(screen))
    score_value = ocr.recognize_number(score_image)
    if score_value is not None:
        score = score_value
        _log.debug('[舰队 OCR] 可用分数: {}', score_value)
    elif fallback_score is not None:
        score = fallback_score
        _log.warning('[舰队 OCR] 分数识别失败，使用上一轮分数: {}', fallback_score)
    else:
        score = 0
        _log.warning('[舰队 OCR] 分数识别失败')

    cost_roi = ROI(
        x1=COST_AREA[0][0],
        y1=COST_AREA[1][1],
        x2=COST_AREA[1][0],
        y2=COST_AREA[0][1],
    )
    cost_results = ocr.recognize(cost_roi.crop(screen), allowlist='0123456789xX')
    cost_results.sort(key=lambda result: result.bbox[0])

    costs: list[int] = []
    for result in cost_results:
        cost = _parse_offer_cost_text(result.text)
        if cost is None:
            _log.debug("[舰队 OCR] 费用解析跳过: '{}'", result.text)
            continue
        costs.append(cost)

    _log.debug('[舰队 OCR] 识别到 {} 项费用: {}', len(costs), costs)
    if any(cost < 4 for cost in costs[:4]):
        _log.warning('[舰队 OCR] 识别到小于 4 的费用，建议检查编队是否有误')

    selections: dict[str, FleetSelection] = {}
    for index, cost in enumerate(costs):
        if cost > score:
            continue
        if index >= len(SHIP_NAME_X_RANGES):
            break

        x_range = SHIP_NAME_X_RANGES[index]
        name_roi = ROI(
            x1=x_range[0],
            y1=SHIP_NAME_Y_RANGE[0],
            x2=x_range[1],
            y2=SHIP_NAME_Y_RANGE[1],
        )
        name_image = name_roi.crop(screen)
        name = ocr.recognize_ship_name(name_image)
        if name is None:
            raw = ocr.recognize_single(name_image)
            name = raw.text.strip() or f'未识别{index}'
            _log.debug("[舰队 OCR] 舰船名模糊匹配失败，原文: '{}'", name)

        click_x = FLEET_CARD_X_POSITIONS[index]
        selections[name] = FleetSelection(
            name=name,
            cost=cost,
            click_position=(click_x, FLEET_CARD_CLICK_Y),
        )

    _log.info('[舰队 OCR] 舰队选项: {}', {name: item.cost for name, item in selections.items()})
    return score, selections


def read_last_offer_name(
    ocr: OCREngine,
    screen: np.ndarray,
) -> str | None:
    """OCR 读取战备舰队浮层最后一张卡片的舰船名。"""
    x_range = SHIP_NAME_X_RANGES[4]
    name_roi = ROI(
        x1=x_range[0],
        y1=SHIP_NAME_Y_RANGE[0],
        x2=x_range[1],
        y2=SHIP_NAME_Y_RANGE[1],
    )
    return ocr.recognize_ship_name(name_roi.crop(screen))


def read_skill_ship_names(
    ocr: OCREngine,
    screen: np.ndarray,
) -> list[str]:
    """OCR 读取副官技能浮层中获得的舰船名称。"""
    result = ocr.recognize_ship_names(ROI.from_tuple(SKILL_SHIP_AREA).crop(screen))
    return list(result) if result is not None else []


def read_available_ship_names(
    ocr: OCREngine,
    screen: np.ndarray,
) -> set[str]:
    """OCR 读取选船列表中当前可见的舰船名称。"""
    return recognize_ships_in_list(ocr, screen)


def read_ship_drop(
    ocr: OCREngine,
    screen: np.ndarray,
) -> ShipDropResult:
    """OCR 读取结算浮层中的掉落舰船名称和舰种。"""
    return recognize_ship_drop(screen, ocr)


def recognize_map_node(
    dll: ApiDll,
    screen: np.ndarray,
    center: float,
) -> str:
    """用地图识别 DLL 读取舰船指示器所在列的节点字母。"""
    height, width = screen.shape[:2]
    x1 = max(0, int((center + NODE_CROP_OFFSET[0]) * width))
    x2 = min(width, int((center + NODE_CROP_OFFSET[1]) * width))
    return dll.recognize_map(screen[0:height, x1:x2])


def _parse_offer_cost_text(text: str) -> int | None:
    """解析费用文本，兼容 ``x4`` 和 ``X4`` 格式。"""
    cleaned = text.strip().replace(' ', '').lstrip('xX')
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _prepare_text_roi(image: np.ndarray, *, scale: int = 4) -> np.ndarray:
    """放大并增强小块 OCR 区域，改善费用和分数识别。"""
    if image.size == 0:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    binary = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)


__all__ = [
    'read_available_ship_names',
    'read_chapter_number',
    'read_last_offer_name',
    'read_ship_drop',
    'read_skill_ship_names',
    'recognize_fleet_options',
    'recognize_map_node',
]
