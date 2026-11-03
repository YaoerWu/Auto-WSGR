"""模块功能：出征页面的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sortie.checker：读取标签模板、浮窗标题模板与识别区域。
- autowsgr.application.controller.sortie.page：读取标签与返回落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名、页面层顺序与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.application.navigation.types import PageName
from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie'

# 五个标签的激活态模板；目录小写、文件名全大写。
# 只保留激活态：标签互斥，一次只有一个激活模板能匹配上。
SORTIE_TAB_TEMPLATE = 'SORTIE_SORTIE_TAB_720P.png'
EXERCISE_TAB_TEMPLATE = 'SORTIE_EXERCISE_TAB_720P.png'
EXPEDITION_TAB_TEMPLATE = 'SORTIE_EXPEDITION_TAB_720P.png'
CAMPAIGN_TAB_TEMPLATE = 'SORTIE_CAMPAIGN_TAB_720P.png'
DECISIVE_TAB_TEMPLATE = 'SORTIE_DECISIVE_TAB_720P.png'

# 演习对手浮窗标题是唯一的浮窗判据：关闭按钮在登录更新弹窗上也能命中 0.95，挑战按钮
# 在无浮窗演习页上能命中 0.78，只有标题模板跨 60+ 张静态图的最高误命中是 0.46。浮窗
# 和标签要在一帧里判层叠关系，所以模板留在本命名空间，不跨 checker 去取。
EXERCISE_OVERLAY_TITLE_TEMPLATE = 'EXERCISE_OVERLAY_TITLE_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；区域由像素框换算为四位小数，并按 [规范]python-code-style.md
# §6.5 外扩，保证区域大于对应模板。

# 标签栏区域由 SORTIE_TAB_ROI_REPORT.json 的像素框换算。
SORTIE_TAB_ROI = ROI(0.1539, 0.0166, 0.2149, 0.0723)
EXERCISE_TAB_ROI = ROI(0.2796, 0.0152, 0.3438, 0.075)
EXPEDITION_TAB_ROI = ROI(0.4078, 0.0138, 0.4735, 0.0764)
CAMPAIGN_TAB_ROI = ROI(0.5367, 0.0138, 0.6008, 0.0764)
DECISIVE_TAB_ROI = ROI(0.6656, 0.0166, 0.7336, 0.075)

# 浮窗标题区域由 演习页ROI_720P.yaml 的 roi_px 换算。
EXERCISE_OVERLAY_TITLE_ROI = ROI(0.075, 0.2264, 0.2133, 0.2778)

# 页面、模板与识别区域，顺序即由深到浅的返回顺序。
# 浮窗出现时顶部标签栏不被遮挡，浮窗和演习标签会同时命中，所以浮窗排最前。
SORTIE_LAYERS: tuple[tuple[PageName, str, ROI], ...] = (
    (PageName.EXERCISE_RIVAL_CONFIRM, EXERCISE_OVERLAY_TITLE_TEMPLATE, EXERCISE_OVERLAY_TITLE_ROI),
    (PageName.SORTIE_MAP, SORTIE_TAB_TEMPLATE, SORTIE_TAB_ROI),
    (PageName.EXERCISE, EXERCISE_TAB_TEMPLATE, EXERCISE_TAB_ROI),
    (PageName.EXPEDITION, EXPEDITION_TAB_TEMPLATE, EXPEDITION_TAB_ROI),
    (PageName.CAMPAIGN, CAMPAIGN_TAB_TEMPLATE, CAMPAIGN_TAB_ROI),
    (PageName.DECISIVE_BATTLE, DECISIVE_TAB_TEMPLATE, DECISIVE_TAB_ROI),
)


# ── 页面壳和顶部标签落点 ────────────────────────────────────────────────────

# 出征区域左上角返回按钮，用于离开出征页回到主页。
CLICK_BACK = (0.0219, 0.0584)

# 坐标为 1280x720 参考画面的归一化值；键与标签名一致。
TAB_POSITIONS: dict[str, tuple[float, float]] = {
    'sortie': (0.1844, 0.0514),  # 出征标签，用于打开普通出征章节页面。
    'exercise': (0.3157, 0.0500),  # 演习标签，用于打开演习对手页面。
    'expedition': (0.4422, 0.0514),  # 远征标签，用于打开远征收取页面。
    'campaign': (0.5750, 0.0459),  # 战役标签，用于打开战役选择页面。
    'decisive': (0.6985, 0.0514),  # 决战标签，用于打开决战入口页面。
}


__all__ = [
    'CAMPAIGN_TAB_ROI',
    'CAMPAIGN_TAB_TEMPLATE',
    'CLICK_BACK',
    'DECISIVE_TAB_ROI',
    'DECISIVE_TAB_TEMPLATE',
    'EXERCISE_OVERLAY_TITLE_ROI',
    'EXERCISE_OVERLAY_TITLE_TEMPLATE',
    'EXERCISE_TAB_ROI',
    'EXERCISE_TAB_TEMPLATE',
    'EXPEDITION_TAB_ROI',
    'EXPEDITION_TAB_TEMPLATE',
    'SORTIE_LAYERS',
    'SORTIE_TAB_ROI',
    'SORTIE_TAB_TEMPLATE',
    'TAB_POSITIONS',
    'TEMPLATE_NAMESPACE',
]
