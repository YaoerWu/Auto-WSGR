"""模块功能：出征准备页的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sortie.battle_preparation.checker：读取准备页模板与识别区域。
- autowsgr.application.controller.sortie.battle_preparation.page：读取返回与舰队标签落点。
- autowsgr.application.controller.sortie.battle_preparation.ship_pool.page：读取返回落点。

下层依赖：
- application.navigation.types：提供页面名。
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名、页面顺序与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.application.navigation.types import PageName
from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation'

# 四个准备页的模板；目录小写、文件名全大写。
BATTLE_PREPARATION_TEMPLATE = 'BATTLE_PREP_720P.png'
DECISIVE_PREPARATION_TEMPLATE = 'DECISIVE_PREP_720P.png'
EXERCISE_PREPARATION_TEMPLATE = 'EXERCISE_PREP_720P.png'
CAMPAIGN_PREPARATION_TEMPLATE = 'CAMPAIGN_PREP_720P.png'

# 四页共用同一块区域，只在右上角三格快捷按钮（预/装备/奖杯）的占用格数上不同。
# 三格全齐的普通页模板放最后，避免最宽松的模板抢先命中其它页。
PREPARATION_TEMPLATES: tuple[tuple[PageName, str], ...] = (
    (PageName.EXERCISE_PREPARATION, EXERCISE_PREPARATION_TEMPLATE),
    (PageName.DECISIVE_BATTLE_PREPARATION, DECISIVE_PREPARATION_TEMPLATE),
    (PageName.CAMPAIGN_PREPARATION, CAMPAIGN_PREPARATION_TEMPLATE),
    (PageName.BATTLE_PREPARATION, BATTLE_PREPARATION_TEMPLATE),
)

# 四个舰队的选中态模板；只有被选中的那一队是亮蓝高亮块，其余三队为暗色。
TEAM_TAB_TEMPLATES: tuple[str, ...] = (
    'TEAM_1_ACTIVE_720P.png',
    'TEAM_2_ACTIVE_720P.png',
    'TEAM_3_ACTIVE_720P.png',
    'TEAM_4_ACTIVE_720P.png',
)


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 出征准备页ROI_720P.yaml 的 roi_px=[767, 99, 928, 140] 换算，
# 区域比 160x40 的模板各边大 1px。
BATTLE_PREPARATION_ROI = ROI(0.5993, 0.1375, 0.725, 0.1945)

# 四个舰队标签页的搜索区，与 TEAM_TAB_TEMPLATES 一一对应，由
# 出征准备页状态ROI_720P.yaml 的 roi_normalized 抄录。
# 四队底色相同、只差队列数字，共享区域会互相误命中（交叉分 0.87 以上），
# 因此每队配一块只容 ±1px 滑动的窄区域；实测交叉分降到 0.72 以下。
TEAM_TAB_ROIS: tuple[ROI, ...] = (
    ROI(0.08125, 0.12777778, 0.1421875, 0.19722222),
    ROI(0.20859375, 0.13055556, 0.26171875, 0.19444444),
    ROI(0.33046875, 0.12916667, 0.38671875, 0.19444444),
    ROI(0.4546875, 0.12777778, 0.5109375, 0.19722222),
)


# ── 页面点击落点 ────────────────────────────────────────────────────────────

# 左上角返回圆环的中心；准备页与船池页共用同一套标题栏布局。
CLICK_BACK = (0.0313, 0.0528)

# 四个舰队标签页的中心，按 1、2、3、4 队顺序；取各自高亮块模板的几何中心。
CLICK_TEAM_TABS: tuple[tuple[float, float], ...] = (
    (0.1113, 0.1618),
    (0.2348, 0.1618),
    (0.3582, 0.1611),
    (0.4824, 0.1618),
)


__all__ = [
    'BATTLE_PREPARATION_ROI',
    'BATTLE_PREPARATION_TEMPLATE',
    'CAMPAIGN_PREPARATION_TEMPLATE',
    'CLICK_BACK',
    'CLICK_TEAM_TABS',
    'DECISIVE_PREPARATION_TEMPLATE',
    'EXERCISE_PREPARATION_TEMPLATE',
    'PREPARATION_TEMPLATES',
    'TEAM_TAB_ROIS',
    'TEAM_TAB_TEMPLATES',
    'TEMPLATE_NAMESPACE',
]
