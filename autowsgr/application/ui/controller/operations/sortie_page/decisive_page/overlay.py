"""模块功能：识别决战地图上的浮层类型和地图页面视觉状态。

上层调用：
- application.ui.controller.operations.sortie_page.decisive_page.map_page：读取浮层和地图状态。
- testing.ui、testing.ops：验证决战浮层和恢复链路。

下层依赖：
- application.ui.controller.operations.sortie_page.decisive_page.constants：提供像素签名。
- common.vision：执行模板和像素签名匹配。

本模块只负责视觉状态识别，不点击设备、不执行 OCR，也不决定决战业务阶段。
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
    SIG_ADVANCE_CHOICE,
    SIG_CONFIRM_EXIT,
    SIG_FLEET_ACQUISITION,
    SIG_MAP_PAGE,
)
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ROI, ImageChecker, ImageTemplate, PixelChecker, PixelSignature


if TYPE_CHECKING:
    import numpy as np


_log = get_logger('ui.decisive')


class DecisiveOverlay(enum.Enum):
    """决战地图上的浮层类型。"""

    FLEET_ACQUISITION = 'fleet_acquisition'
    """战备舰队获取浮层，用于选择购买舰船或技能。"""

    CONFIRM_EXIT = 'confirm_exit'
    """退出确认浮层，用于选择暂离或撤退。"""

    ADVANCE_CHOICE = 'advance_choice'
    """前进路线选择浮层，用于选择决战分支路线。"""


_OVERLAY_SIGNATURES: tuple[tuple[DecisiveOverlay, PixelSignature], ...] = (
    (DecisiveOverlay.FLEET_ACQUISITION, SIG_FLEET_ACQUISITION),
    (DecisiveOverlay.CONFIRM_EXIT, SIG_CONFIRM_EXIT),
    (DecisiveOverlay.ADVANCE_CHOICE, SIG_ADVANCE_CHOICE),
)
_SIG_BY_TYPE = dict(_OVERLAY_SIGNATURES)
_OVERLAY_TEMPLATE_MAP: dict[DecisiveOverlay, ImageTemplate] = {
    DecisiveOverlay.FLEET_ACQUISITION: Templates.Decisive.FLEET_ACQUISITION,
    DecisiveOverlay.CONFIRM_EXIT: Templates.Decisive.CONFIRM_EXIT,
    DecisiveOverlay.ADVANCE_CHOICE: Templates.Decisive.ADVANCE_CHOICE,
}

# Overlay templates are collected at 1280x720. Keep a one-pixel margin so
# scaled screenshots do not lose a match at the crop boundary.
USE_LAST_FLEET_ROI = ROI(0.82, 0.30, 1.0, 0.50).expand_pixels(1280, 720)
FLEET_NAME_ROI = ROI(0.08, 0.11, 0.26, 0.22).expand_pixels(1280, 720)
FLEET_ACQUISITION_ROI = ROI(
    494 / 1280,
    38 / 720,
    799 / 1280,
    107 / 720,
).expand_pixels(1280, 720)
CONFIRM_EXIT_ROI = ROI(
    363 / 1280,
    161 / 720,
    917 / 1280,
    465 / 720,
).expand_pixels(1280, 720)
ADVANCE_CHOICE_ROI = ROI(
    324 / 1280,
    237 / 720,
    607 / 1280,
    429 / 720,
).expand_pixels(1280, 720)
ADVANCE_CHOICE_THREE_ROI = ROI(
    142 / 1280,
    235 / 720,
    429 / 1280,
    431 / 720,
).expand_pixels(1280, 720)

_FLEET_ACQUISITION_CONFIDENCE = 0.70
_ADVANCE_CHOICE_CONFIDENCE = 0.80


def check_decisive_map_page(screen: np.ndarray) -> bool:
    """检查截图是否为没有浮层遮挡的决战地图页。"""
    return PixelChecker.check_signature(screen, SIG_MAP_PAGE).matched


def check_fleet_acquisition(screen: np.ndarray) -> bool:
    """检查截图是否为战备舰队获取浮层。"""
    return ImageChecker.template_exists(
        screen,
        Templates.Decisive.FLEET_ACQUISITION,
        roi=FLEET_ACQUISITION_ROI,
        confidence=_FLEET_ACQUISITION_CONFIDENCE,
    )


def detect_decisive_overlay(
    screen: np.ndarray,
    *,
    advance_choice_roi: ROI | None = None,
    include_fleet_acquisition: bool = True,
) -> DecisiveOverlay | None:
    """按优先级检测决战浮层，可按入口阶段屏蔽已消费的浮层。"""
    for overlay_type, template in _OVERLAY_TEMPLATE_MAP.items():
        if overlay_type is DecisiveOverlay.FLEET_ACQUISITION and not include_fleet_acquisition:
            continue

        confidence = (
            _FLEET_ACQUISITION_CONFIDENCE
            if overlay_type is DecisiveOverlay.FLEET_ACQUISITION
            else _ADVANCE_CHOICE_CONFIDENCE
            if overlay_type is DecisiveOverlay.ADVANCE_CHOICE
            else 0.85
        )
        if overlay_type is DecisiveOverlay.ADVANCE_CHOICE:
            rois = (
                (advance_choice_roi, ADVANCE_CHOICE_ROI, ADVANCE_CHOICE_THREE_ROI)
                if advance_choice_roi is not None
                else (ADVANCE_CHOICE_ROI, ADVANCE_CHOICE_THREE_ROI)
            )
            matched = any(
                ImageChecker.template_exists(screen, template, roi=roi, confidence=confidence)
                for roi in rois
            )
        else:
            roi = (
                FLEET_ACQUISITION_ROI
                if overlay_type is DecisiveOverlay.FLEET_ACQUISITION
                else CONFIRM_EXIT_ROI
                if overlay_type is DecisiveOverlay.CONFIRM_EXIT
                else None
            )
            matched = ImageChecker.template_exists(
                screen,
                template,
                roi=roi,
                confidence=confidence,
            )

        if matched:
            _log.debug('[决战] 检测到浮层: {}', overlay_type.value)
            return overlay_type
    return None


def read_overlay_type(screen: np.ndarray) -> DecisiveOverlay | None:
    """按优先级读取截图中的决战浮层类型。

    Args:
        screen: RGB 截图。

    Returns:
        首个匹配的浮层类型；没有浮层时返回 ``None``。
    """
    return detect_decisive_overlay(screen)


def read_overlay_template(overlay: DecisiveOverlay) -> ImageTemplate:
    """读取指定浮层对应的模板。"""
    return _OVERLAY_TEMPLATE_MAP[overlay]


def read_overlay_signature(overlay: DecisiveOverlay) -> PixelSignature:
    """读取指定浮层对应的像素签名。"""
    return _SIG_BY_TYPE[overlay]


__all__ = [
    'ADVANCE_CHOICE_ROI',
    'ADVANCE_CHOICE_THREE_ROI',
    'CONFIRM_EXIT_ROI',
    'FLEET_ACQUISITION_ROI',
    'FLEET_NAME_ROI',
    'USE_LAST_FLEET_ROI',
    'DecisiveOverlay',
    'check_decisive_map_page',
    'check_fleet_acquisition',
    'detect_decisive_overlay',
    'read_overlay_signature',
    'read_overlay_template',
    'read_overlay_type',
]
