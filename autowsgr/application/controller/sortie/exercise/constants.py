"""模块功能：演习页与对手详情浮窗的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sortie.exercise.checker：读取模板名、识别区域与解析规则。
- autowsgr.application.controller.sortie.exercise.page：读取滑动与点击落点。

下层依赖：
- application.controller.types：舰种枚举。
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名、解析规则与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

import re

from autowsgr.application.controller.types import ShipType
from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/exercise'

# 三个按钮只用来定位点击中心，不作浮窗判据：关闭按钮在登录更新弹窗上也能命中
# 0.95，挑战按钮在无浮窗演习页上能命中 0.78。浮窗判据是标题模板，由
# sortie.checker 持有，好让浮窗和标签在一帧里判层叠关系。
OVERLAY_CLOSE_TEMPLATE = 'EXERCISE_OVERLAY_CLOSE_720P.png'
OVERLAY_REFRESH_TEMPLATE = 'EXERCISE_OVERLAY_REFRESH_720P.png'
OVERLAY_CHALLENGE_TEMPLATE = 'EXERCISE_OVERLAY_CHALLENGE_720P.png'

# 浮窗固定展示六个对手，槽位号即序列下标加一。
EXERCISE_RIVAL_SLOTS = 6

# 等级文字形如 LV.110，白名单只留 LV 字母、数字与小数点，避免其它符号噪声混入。
LEVEL_ALLOWLIST = 'LV0123456789.'


# 舰种名到枚举值的反查表；枚举值是游戏里的中文舰种全称。
SHIP_TYPE_BY_NAME = {member.value: member for member in ShipType if member is not ShipType.Other}

# 等级文字取第一段数字，浮窗该区域只框住「LV.110」，没有星级干扰。
LEVEL_REGEX = re.compile(r'(\d+)')


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 演习页ROI_720P.yaml 的 roi_px 换算，区域比模板各边大 1px。
OVERLAY_CLOSE_ROI = ROI(0.9, 0.2306, 0.9321, 0.2778)
OVERLAY_REFRESH_ROI = ROI(0.6485, 0.707, 0.7727, 0.7681)
OVERLAY_CHALLENGE_ROI = ROI(0.7891, 0.7098, 0.9149, 0.7695)

# 六个槽位的舰种文字区，从左到右；不含国籍括号，校准基准 1280x720。
RIVAL_SHIP_TYPE_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.5750, 0.3250, 0.6084),
    ROI(0.3945, 0.5750, 0.4321, 0.6084),
    ROI(0.5023, 0.5750, 0.5399, 0.6084),
    ROI(0.6093, 0.5750, 0.6469, 0.6084),
    ROI(0.7171, 0.5750, 0.7547, 0.6084),
    ROI(0.8250, 0.5750, 0.8625, 0.6084),
)

# 六个槽位的等级文字区，上边界紧接舰种区；不含星级，校准基准 1280x720。
RIVAL_SHIP_LEVEL_ROIS: tuple[ROI, ...] = (
    ROI(0.2875, 0.6084, 0.3297, 0.6320),
    ROI(0.3945, 0.6084, 0.4368, 0.6320),
    ROI(0.5023, 0.6084, 0.5446, 0.6320),
    ROI(0.6093, 0.6084, 0.6516, 0.6320),
    ROI(0.7171, 0.6084, 0.7594, 0.6320),
    ROI(0.8250, 0.6084, 0.8672, 0.6320),
)


# ── 演习页落点 ──────────────────────────────────────────────────────────────

# 首屏四个对手的挑战按钮中心，按屏幕从上到下排列；x 四格一致。
RIVAL_CHALLENGE_POSITIONS: tuple[tuple[float, float], ...] = (
    (0.8449, 0.2104),
    (0.8449, 0.4160),
    (0.8449, 0.6215),
    (0.8449, 0.8271),
)

# 列表手势：滑到顶让对手 1-4 落在首屏，滑到底让对手 5 落在首屏第四格。
SWIPE_TO_TOP: tuple[float, float, float, float] = (0.8336, 0.3709, 0.8336, 0.7403)
SWIPE_TO_BOTTOM: tuple[float, float, float, float] = (0.8336, 0.7403, 0.8336, 0.3709)

# 三个浮窗按钮的固定落点；识别到模板中心时优先用中心，读不到才回落到这里。
CLICK_OVERLAY_CLOSE: tuple[float, float] = (0.9156, 0.2535)
CLICK_OVERLAY_REFRESH: tuple[float, float] = (0.7102, 0.7368)
CLICK_OVERLAY_CHALLENGE: tuple[float, float] = (0.8516, 0.7389)

# 首屏可见对手槽位数；对手 5 要滑到底后落在第四格。
VISIBLE_RIVAL_SLOTS = 4


__all__ = [
    'CLICK_OVERLAY_CHALLENGE',
    'CLICK_OVERLAY_CLOSE',
    'CLICK_OVERLAY_REFRESH',
    'EXERCISE_RIVAL_SLOTS',
    'LEVEL_ALLOWLIST',
    'LEVEL_REGEX',
    'OVERLAY_CHALLENGE_ROI',
    'OVERLAY_CHALLENGE_TEMPLATE',
    'OVERLAY_CLOSE_ROI',
    'OVERLAY_CLOSE_TEMPLATE',
    'OVERLAY_REFRESH_ROI',
    'OVERLAY_REFRESH_TEMPLATE',
    'RIVAL_CHALLENGE_POSITIONS',
    'RIVAL_SHIP_LEVEL_ROIS',
    'RIVAL_SHIP_TYPE_ROIS',
    'SHIP_TYPE_BY_NAME',
    'SWIPE_TO_BOTTOM',
    'SWIPE_TO_TOP',
    'TEMPLATE_NAMESPACE',
    'VISIBLE_RIVAL_SLOTS',
]
