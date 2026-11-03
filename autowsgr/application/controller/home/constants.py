"""模块功能：主页的识别数据与点击落点。

上层调用：
- application.controller.home.checker：读取模板名、识别区域与一帧探测清单。
- application.controller.home.page：读取导航与每日浮窗按钮的点击落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/home'

# 本模块的模板文件名；目录小写、文件名全大写。
HOME_MAIN_TEMPLATE = 'HOME_MAIN_720P.png'
NEWS_TEXT_TEMPLATE = 'HOME_NEWS_TEXT_720P.png'
NEWS_CHECKED_TEMPLATE = 'HOME_NEWS_CHECKBOX_CHECKED_720P.png'
NEWS_UNCHECKED_TEMPLATE = 'HOME_NEWS_CHECKBOX_UNCHECKED_720P.png'
REWARD_TEXT_TEMPLATE = 'HOME_REWARD_TEXT_720P.png'
REWARD_CLAIM_TEMPLATE = 'HOME_REWARD_CLAIM_BUTTON_720P.png'
REWARD_CONFIRM_TEMPLATE = 'HOME_REWARD_CONFIRM_BUTTON_720P.png'

# 主页入口图标的归一化区域，校准基准为 1280x720 截图。
HOME_MAIN_ROI = ROI(0.9109, 0.8681, 0.9758, 0.9139)

# 公告浮窗文字区域与勾选框区域。
NEWS_TEXT_ROI = ROI(0.0867, 0.8763, 0.2125, 0.9403)
NEWS_CHECKBOX_ROI = ROI(0.0382, 0.8652, 0.0875, 0.9459)

# 每日奖励浮窗的文字区域与领取按钮区域。
REWARD_TEXT_ROI = ROI(0.1015, 0.268, 0.3313, 0.3362)
REWARD_CLAIM_BUTTON_ROI = ROI(0.4406, 0.6291, 0.5594, 0.7028)

# 每日奖励确认浮窗的确认按钮区域。
REWARD_CONFIRM_BUTTON_ROI = ROI(0.4351, 0.5194, 0.5696, 0.6209)

# 一帧要读的七个模板，顺序固定；解包时的下标顺序以这里为准。
HOME_PROBES: tuple[tuple[str, ROI], ...] = (
    (HOME_MAIN_TEMPLATE, HOME_MAIN_ROI),
    (NEWS_TEXT_TEMPLATE, NEWS_TEXT_ROI),
    (NEWS_CHECKED_TEMPLATE, NEWS_CHECKBOX_ROI),
    (NEWS_UNCHECKED_TEMPLATE, NEWS_CHECKBOX_ROI),
    (REWARD_TEXT_TEMPLATE, REWARD_TEXT_ROI),
    (REWARD_CLAIM_TEMPLATE, REWARD_CLAIM_BUTTON_ROI),
    (REWARD_CONFIRM_TEMPLATE, REWARD_CONFIRM_BUTTON_ROI),
)


# ── 主页导航落点 ────────────────────────────────────────────────────────────

# 坐标为 1280x720 参考画面的归一化值；键与 Target 枚举名一致。
NAV_POSITIONS = {
    'sortie': (0.9430, 0.9069),
    'task': (0.6844, 0.9326),
    'sidebar': (0.0480, 0.8931),
    'backyard': (0.0508, 0.1535),
    'event': (0.8844, 0.4833),
}


# ── 每日浮窗按钮落点 ────────────────────────────────────────────────────────

# 坐标为 1280x720 归一化值，由静态样本做模板匹配实测（score=1.000）。
OVERLAY_POSITIONS = {
    'news_checkbox': (0.0625, 0.9049),
    'news_close': (0.0352, 0.0625),
    'reward_claim': (0.5000, 0.6653),
    'reward_confirm': (0.5020, 0.5694),
}


__all__ = [
    'HOME_MAIN_ROI',
    'HOME_MAIN_TEMPLATE',
    'HOME_PROBES',
    'NAV_POSITIONS',
    'NEWS_CHECKBOX_ROI',
    'NEWS_CHECKED_TEMPLATE',
    'NEWS_TEXT_ROI',
    'NEWS_TEXT_TEMPLATE',
    'NEWS_UNCHECKED_TEMPLATE',
    'OVERLAY_POSITIONS',
    'REWARD_CLAIM_BUTTON_ROI',
    'REWARD_CLAIM_TEMPLATE',
    'REWARD_CONFIRM_BUTTON_ROI',
    'REWARD_CONFIRM_TEMPLATE',
    'REWARD_TEXT_ROI',
    'REWARD_TEXT_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
