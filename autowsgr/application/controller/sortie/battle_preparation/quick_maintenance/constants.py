"""模块功能：快速整备区域的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.checker：读取模板名与识别区域。
- autowsgr.application.controller.sortie.battle_preparation.quick_maintenance.page：读取点击落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation/quick_maintenance'

# 左下角自动补给勾选框的开启态；只认开启，勾选框没勾上即视为未开启。
AUTO_SUPPLY_TEMPLATE = 'AUTO_SUPPLY_ON_720P.png'

# 底部功能栏快速修理页签的激活态；页签未激活时与激活模板的相关系数明显低于阈值。
QUICK_REPAIR_TEMPLATE = 'QUICK_REPAIR_ACTIVE_720P.png'

# 修理面板右侧的「全部修理」按钮；页签激活后右侧面板约 1.5-2 秒才联动弹出，
# 只有它出现才说明真的进了修理视图（补给视图的「全部补给」同款同位置，靠模板分不开）。
ALL_REPAIR_BUTTON_TEMPLATE = 'ALL_REPAIR_BUTTON_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720。自动补给勾选框像素范围 [38, 645, 93, 702]，
# 比 54x56 的模板各边大 1px。
AUTO_SUPPLY_ROI = ROI(0.0297, 0.8958, 0.0727, 0.975)

# 快速修理页签像素范围 [469, 538, 651, 590]；限定在页签附近搜索，
# 防止 179x49 的模板滑到右侧「快速补给」页签上。
QUICK_REPAIR_ROI = ROI(0.3664, 0.7472, 0.5086, 0.8194)

# 「全部修理」按钮像素范围 [1022, 464, 1174, 518]，比 151x53 的模板各边大 1px。
ALL_REPAIR_BUTTON_ROI = ROI(0.7984375, 0.64444444, 0.9171875, 0.71944444)

# 修理道具存量文字像素范围 [1136, 398, 1204, 432]；左边界贴着数字前的斜杠右侧，
# 再往左会把斜杠读成数字 1。
REPAIR_STOCK_ROI = ROI(0.8875, 0.55277778, 0.940625, 0.6)


# ── 页面点击落点 ────────────────────────────────────────────────────────────

# 左下角自动补给勾选框的中心；框体像素范围 [38, 645, 92, 701]。
CLICK_AUTO_SUPPLY = (0.0508, 0.9347)

# 底部功能栏快速修理页签的中心；页签像素范围 [470, 539, 649, 588]。
CLICK_QUICK_REPAIR = (0.4371, 0.7826)

# 右侧修理面板「全部修理」按钮的中心；按钮像素范围 [1022, 464, 1173, 517]。
CLICK_ALL_REPAIR = (0.8578, 0.6819)


__all__ = [
    'ALL_REPAIR_BUTTON_ROI',
    'ALL_REPAIR_BUTTON_TEMPLATE',
    'AUTO_SUPPLY_ROI',
    'AUTO_SUPPLY_TEMPLATE',
    'CLICK_ALL_REPAIR',
    'CLICK_AUTO_SUPPLY',
    'CLICK_QUICK_REPAIR',
    'QUICK_REPAIR_ROI',
    'QUICK_REPAIR_TEMPLATE',
    'REPAIR_STOCK_ROI',
    'TEMPLATE_NAMESPACE',
]
