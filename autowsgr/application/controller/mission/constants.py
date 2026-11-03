"""模块功能：任务页的识别数据与点击落点。

上层调用：
- application.controller.mission.checker：读取模板名与识别区域。
- application.controller.mission.page：读取领奖与返回按钮的点击落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/mission'

# 本模块的模板文件名；目录小写、文件名全大写。
# 任务页默认落在「全部」页签，因此用它作为页面身份。
ALL_TAB_TEMPLATE = 'MISSION_ALL_TAB_720P.png'
CLAIM_ALL_BUTTON_TEMPLATE = 'MISSION_CLAIM_ALL_720P.png'
REWARD_CONFIRM_BUTTON_TEMPLATE = 'MISSION_REWARD_CONFIRM_720P.png'


# ── 任务页识别区域 ──────────────────────────────────────────────────────────

# 顶部「全部」页签的归一化区域，校准基准为 1280x720 截图。
ALL_TAB_ROI = ROI(0.1477, 0.0223, 0.2204, 0.0848)


# ── 领奖与确认区域 ──────────────────────────────────────────────────────────

# 右下角「全部领取」按钮与「获得」浮窗里的「确认」按钮，同一校准基准。
CLAIM_ALL_BUTTON_ROI = ROI(0.8157, 0.9181, 0.9243, 0.9848)
REWARD_CONFIRM_BUTTON_ROI = ROI(0.4399, 0.6098, 0.554, 0.6889)


# ── 任务页导航落点 ──────────────────────────────────────────────────────────

# 左上角返回按钮；任务页与出征页、好友页、建造页、改造页的返回按钮落在同一位置。
CLICK_BACK = (0.0219, 0.0584)


# ── 任务页点击落点 ──────────────────────────────────────────────────────────

# 右下角「全部领取」按钮，只在有奖励可领时出现。
CLICK_CLAIM_ALL = (0.8695, 0.9507)
# 「获得」浮窗里的「确认」按钮。
CLICK_REWARD_CONFIRM = (0.4965, 0.6486)


__all__ = [
    'ALL_TAB_ROI',
    'ALL_TAB_TEMPLATE',
    'CLAIM_ALL_BUTTON_ROI',
    'CLAIM_ALL_BUTTON_TEMPLATE',
    'CLICK_BACK',
    'CLICK_CLAIM_ALL',
    'CLICK_REWARD_CONFIRM',
    'REWARD_CONFIRM_BUTTON_ROI',
    'REWARD_CONFIRM_BUTTON_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
