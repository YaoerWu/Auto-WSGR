"""模块功能：地图画面的单帧观测。

上层调用：
- application.combat.node_tracking.tracker：每轮地图画面读一次小船位置，
  并判断当前是不是索敌页。

下层依赖：
- controller.sortie.battle_engine.monitor.checker：索敌页判定复用阶段识别。
- controller.sortie.battle_engine.tracking.constants：黄色簇与小船图标的像素校准。
- common.vision：截图与像素签名匹配。

边界：只回答"黄色簇在哪、是不是小船、是不是索敌页"；不读地图数据、不判定节点。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import cv2
import numpy

from autowsgr.application.controller.sortie.battle_engine.monitor.checker import (
    read_phase_from_frame,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase
from autowsgr.application.controller.sortie.battle_engine.tracking.constants import (
    SHIP_CENTER_COLOR,
    SHIP_PIXEL_SIDE_OFFSET,
    SHIP_PIXEL_TOLERANCE,
    SHIP_SIDE_COLOR,
    YELLOW_BLUE_MAX,
    YELLOW_BLUE_MIN,
    YELLOW_GREEN_MIN,
    YELLOW_MIN_AREA,
    YELLOW_RED_MIN,
)
from autowsgr.common.vision import MatchStrategy, PixelRule, PixelSignature, adapters, screenshot


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle

_SHIP_PIXEL_SIGNATURE_NAME = 'ship_icon'


def read_ship_position(ctx: ContextHandle) -> tuple[float, float] | None:
    """截图一次，读地图上小船图标的归一化坐标。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。

    Returns:
        小船归一化坐标；没找到、像素验证失败或当前不是地图页时为空。
    """
    return read_ship_position_from_frame(screenshot(ctx))


def read_ship_position_from_frame(frame: numpy.ndarray) -> tuple[float, float] | None:
    """在给定帧上读小船图标的归一化坐标。

    索敌页上也有黄色元素，先排除索敌页再找簇，避免把战斗界面当成地图去追船。

    Args:
        frame: 当前截图帧。

    Returns:
        小船归一化坐标；没找到或像素验证失败时为空。
    """
    if check_spot_page(frame):
        return None
    center = read_yellow_cluster(frame)
    if center is None:
        return None
    if not check_ship_icon(frame, center):
        return None
    return center


def read_yellow_cluster(frame: numpy.ndarray) -> tuple[float, float] | None:
    """找画面里最大的黄色像素簇，返回质心的归一化坐标。

    小船图标是地图上最醒目的黄色块，按面积取最大簇可以避开零星的高亮噪点。

    Args:
        frame: 当前截图帧。

    Returns:
        最大黄色簇的归一化质心；没有足够大的簇时为空。
    """
    red, green, blue = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
    mask = (
        (red.astype(numpy.int16) > YELLOW_RED_MIN)
        & (green.astype(numpy.int16) > YELLOW_GREEN_MIN)
        & (blue.astype(numpy.int16) > YELLOW_BLUE_MIN)
        & (blue.astype(numpy.int16) < YELLOW_BLUE_MAX)
    ).astype(numpy.uint8)

    label_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if label_count <= 1:
        return None

    best_label = -1
    best_area = 0
    for label in range(1, label_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= YELLOW_MIN_AREA and area > best_area:
            best_area = area
            best_label = label
    if best_label < 0:
        return None

    height, width = frame.shape[:2]
    center_x, center_y = centroids[best_label]
    return (center_x / width, center_y / height)


def check_ship_icon(frame: numpy.ndarray, center: tuple[float, float]) -> bool:
    """验证候选点中心与左右两侧都符合小船图标的像素特征。

    只靠黄色簇会在选中高亮、爆炸特效上误判，三点一起验能滤掉这些干扰。

    Args:
        frame: 当前截图帧。
        center: 候选点的归一化坐标。

    Returns:
        三点全部命中返回真。
    """
    center_x, center_y = center
    rules = (
        PixelRule.of(center_x, center_y, SHIP_CENTER_COLOR, tolerance=SHIP_PIXEL_TOLERANCE),
        PixelRule.of(
            center_x - SHIP_PIXEL_SIDE_OFFSET,
            center_y,
            SHIP_SIDE_COLOR,
            tolerance=SHIP_PIXEL_TOLERANCE,
        ),
        PixelRule.of(
            center_x + SHIP_PIXEL_SIDE_OFFSET,
            center_y,
            SHIP_SIDE_COLOR,
            tolerance=SHIP_PIXEL_TOLERANCE,
        ),
    )
    signature = PixelSignature(
        name=_SHIP_PIXEL_SIGNATURE_NAME,
        strategy=MatchStrategy.ALL,
        rules=rules,
    )
    return adapters.match_pixels(frame, signature)[0].matched


def check_spot_page(frame: numpy.ndarray) -> bool:
    """判断给定帧是不是索敌成功页。

    Args:
        frame: 当前截图帧。

    Returns:
        是索敌页返回真。
    """
    return read_phase_from_frame(frame, [CombatPhase.SPOT_ENEMY_SUCCESS]) is not None


__all__ = [
    'check_ship_icon',
    'check_spot_page',
    'read_ship_position',
    'read_ship_position_from_frame',
    'read_yellow_cluster',
]
