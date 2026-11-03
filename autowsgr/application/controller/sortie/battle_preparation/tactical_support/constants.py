"""模块功能：战术支援按钮与浮窗的识别数据。

上层调用：
- application.controller.sortie.battle_preparation.tactical_support.checker：读取本模块常量。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域与模板名，不保存点击落点、不保存开启策略。
"""

from __future__ import annotations

import re

from autowsgr.common.vision import ROI


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation/tactical_support'

# 右上角三格快捷按钮里的第二格，校准基准 1280x720。
# 由 战术支援ROI_720P.yaml 的 roi_px=[819, 90, 876, 149] 换算：区域比 56x58 的模板各边大 1px。
# 只允许 ±1px 滑动：演习页同一格是蓝底「预」字按钮，放大搜索范围会互相误命中。
TACTICAL_SUPPORT_ROI = ROI(0.63984375, 0.125, 0.684375, 0.20694444)

# 已开启态的按钮模板：橙底圆环，与未开启态的蓝底圆环只差底色。
# 不保留未开启模板：匹配到就是已开启，匹配不到就是没开启或这个页面没有这个按钮。
TACTICAL_SUPPORT_ACTIVE_TEMPLATE = 'TACTICAL_SUPPORT_ON_720P.png'

# 浮窗里的开关按钮文字区，读出「未启用」或「已启用」；两态底色完全相同，只能靠文字。
TACTICAL_SUPPORT_TOGGLE_ROI = ROI(0.71484375, 0.45555556, 0.8671875, 0.55)

# 浮窗右下角的剩余次数区，读出「本日剩余次数：10/10」。
TACTICAL_SUPPORT_COUNT_ROI = ROI(0.6875, 0.54861111, 0.90625, 0.61805556)


# 浮窗开关按钮的两种文案，顺序与已启用/未启用一致。
TOGGLE_TEXTS: tuple[str, ...] = ('未启用', '已启用')

# 浮窗右下角的剩余次数，形如「本日剩余次数：10/10」。
COUNT_PATTERN = re.compile(r'(?P<remaining>\d+)\s*/\s*(?P<total>\d+)')

# 右上角第二格战术支援按钮的中心，取已开启态模板的几何中心。
CLICK_SUPPORT_BUTTON = (0.6617, 0.1653)

# 浮窗里开关按钮的中心；开关文案随状态变化，落点不变。
CLICK_TOGGLE_BUTTON = (0.7906, 0.5028)


__all__ = [
    'CLICK_SUPPORT_BUTTON',
    'CLICK_TOGGLE_BUTTON',
    'COUNT_PATTERN',
    'TACTICAL_SUPPORT_ACTIVE_TEMPLATE',
    'TACTICAL_SUPPORT_COUNT_ROI',
    'TACTICAL_SUPPORT_ROI',
    'TACTICAL_SUPPORT_TOGGLE_ROI',
    'TEMPLATE_NAMESPACE',
    'TOGGLE_TEXTS',
]
