"""模块功能：建造页的识别数据与点击落点。

上层调用：
- application.controller.sidebar.build.checker：读取模板名与识别区域。
- application.controller.sidebar.build.page：读取标签与返回落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间：建造页从侧边栏进入，因此嵌在 sidebar 命名空间下。
TEMPLATE_NAMESPACE = 'controller/sidebar/build'

# 本模块的模板文件名；目录小写、文件名全大写。
# 建造页默认落在「建造」标签，因此用它作为页面身份。
BUILD_TAB_TEMPLATE = 'BUILD_TAB_720P.png'
DISMANTLE_TAB_TEMPLATE = 'BUILD_DISMANTLE_TAB_720P.png'


# ── 建造页面识别区域 ────────────────────────────────────────────────────────

# 建造页四个标签中已采样的两个；校准基准为 1280x720 截图。
BUILD_TAB_ROI = ROI(0.1485, 0.0167, 0.2188, 0.0792)
DISMANTLE_TAB_ROI = ROI(0.2782, 0.0153, 0.3469, 0.0806)


# ── 页面与标签坐标 ──────────────────────────────────────────────────────────

# 左上角返回按钮；建造页与出征页、好友页、强化页的返回按钮落在同一位置。
CLICK_BACK: tuple[float, float] = (0.0219, 0.0584)

# 坐标为 1280x720 参考画面的归一化值；建造与解体取自激活标签模板的中心，
# 开发与废弃暂沿用等距估算值（尚未采到激活模板）。
TAB_POSITIONS: dict[str, tuple[float, float]] = {
    'build': (0.1832, 0.0472),  # 顶部建造标签，用于进入舰船建造内容。
    'destroy': (0.3121, 0.0472),  # 顶部解体标签，用于进入舰船解装内容。
    'develop': (0.4375, 0.0458),  # 顶部开发标签，用于进入装备开发内容。
    'discard': (0.5625, 0.0458),  # 顶部废弃标签，用于进入废弃内容。
}


__all__ = [
    'BUILD_TAB_ROI',
    'BUILD_TAB_TEMPLATE',
    'CLICK_BACK',
    'DISMANTLE_TAB_ROI',
    'DISMANTLE_TAB_TEMPLATE',
    'TAB_POSITIONS',
    'TEMPLATE_NAMESPACE',
]
