"""模块功能：船池页面的识别数据。

上层调用：
- application.controller.sortie.battle_preparation.ship_pool.checker：读取本模块常量。

下层依赖：
- common.vision：提供识别区域与像素签名类型。

边界：只保存识别区域、模板名与页面签名，不保存点击落点、不保存选船规则。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI, Color, PixelRule, PixelSignature


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation/ship_pool'

# 船卡列表的正文区，校准基准 1280x720。左边界从 0 起、右边界停在 1048px：
# 再往右是滚动条与右侧信息栏。顶部切掉筛选页签，底部切掉功能按钮栏。
SHIP_LIST_ROI = ROI(0.0, 0.12, 0.81875, 0.95)


# ── 船池分类模板 ────────────────────────────────────────────────────────────

# 船池页是按入口分家的：学院、强化、拆解各有一个专属按钮，出征与活动出征共用
# 一组按钮，决战与它们共用同一排按钮但少了标记星标。四个特征两两组合即可定类，
# 且六页的「排列顺序 / 类型」位置完全相同，不能拿它当判据。
#
# 每个模板只允许在自己那 1px 扩边的死区域里滑动：全图搜索时「快速编队」在出征、
# 演习、决战三页互为 1.0000，「快速选择」对出征页也有 0.9387，阈值分不开。

# 右侧「快速编队」按钮：出征、活动出征、演习、决战四类船池都有。
QUICK_FORMATION_TEMPLATE = 'SHIP_POOL_QUICK_FORMATION_720P.png'
QUICK_FORMATION_ROI = ROI(0.846875, 0.27083333, 0.9765625, 0.35)

# 右侧「快速选择」按钮：只有拆解船池有。
QUICK_SELECT_TEMPLATE = 'SHIP_POOL_QUICK_SELECT_720P.png'
QUICK_SELECT_ROI = ROI(0.846875, 0.26527778, 0.9765625, 0.34444444)

# 右侧「强化满 隐藏」筛选：只有强化船池有。
QUICK_STRENGTHEN_TEMPLATE = 'SHIP_POOL_QUICK_STRENGTHEN_720P.png'
QUICK_STRENGTHEN_ROI = ROI(0.84765625, 0.27083333, 0.97734375, 0.35)

# 「全部舰船」按钮右侧的标记星标：决战船池没有星标，顶部写着决战选船不能用标记筛选。
STAR_TEMPLATE = 'SHIP_POOL_STAR_720P.png'
STAR_ROI = ROI(0.93828125, 0.17361111, 0.9796875, 0.24722222)


# ── 页面签名 ────────────────────────────────────────────────────────────────

# 搜索输入态的页面签名：软键盘上排三个键位，三条规则全部命中才成立。
SEARCH_INPUT_SIGNATURE = PixelSignature(
    'ship_pool_input',
    (
        PixelRule(0.3109, 0.9417, Color(253, 253, 253)),
        PixelRule(0.4437, 0.9417, Color(253, 253, 253)),
        PixelRule(0.5883, 0.9347, Color(253, 253, 253)),
    ),
)


# ── 校准 ────────────────────────────────────────────────────────────────────

# 搜索输入框的中心。
CLICK_SEARCH_BOX = (0.7292, 0.0556)

# 软键盘右上角的收起按钮。
CLICK_DISMISS_KEYBOARD = (0.5208, 0.0926)

# 提交搜索框内容用的回车键（KEYCODE_ENTER）。
KEYCODE_ENTER = 66

# 卡片详情页的「移除舰船」按钮。
CLICK_REMOVE_SHIP = (0.0865, 0.3093)

# 列表的纵向滑动区间：从下往上拖一屏，用于看后面的卡片。
SCROLL_START = (0.4, 0.55)
SCROLL_END = (0.4, 0.30)
SCROLL_DURATION_SECONDS = 0.4


# 判定船池类别的模板与区域，顺序即判定优先级。
KIND_FEATURES: tuple[tuple[str, ROI], ...] = (
    (QUICK_STRENGTHEN_TEMPLATE, QUICK_STRENGTHEN_ROI),
    (QUICK_SELECT_TEMPLATE, QUICK_SELECT_ROI),
    (QUICK_FORMATION_TEMPLATE, QUICK_FORMATION_ROI),
    (STAR_TEMPLATE, STAR_ROI),
)


__all__ = [
    'CLICK_DISMISS_KEYBOARD',
    'CLICK_REMOVE_SHIP',
    'CLICK_SEARCH_BOX',
    'KEYCODE_ENTER',
    'KIND_FEATURES',
    'QUICK_FORMATION_ROI',
    'QUICK_FORMATION_TEMPLATE',
    'QUICK_SELECT_ROI',
    'QUICK_SELECT_TEMPLATE',
    'QUICK_STRENGTHEN_ROI',
    'QUICK_STRENGTHEN_TEMPLATE',
    'SCROLL_DURATION_SECONDS',
    'SCROLL_END',
    'SCROLL_START',
    'SEARCH_INPUT_SIGNATURE',
    'SHIP_LIST_ROI',
    'STAR_ROI',
    'STAR_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
