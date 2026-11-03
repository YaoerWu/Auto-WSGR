"""模块功能：改造页面的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sidebar.intensify.checker：读取模板名与识别区域。
- autowsgr.application.controller.sidebar.intensify.page：读取标签与返回落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间：改造页从侧边栏进入，因此嵌在 sidebar 命名空间下。
TEMPLATE_NAMESPACE = 'controller/sidebar/intensify'

# 本模块的模板文件名；目录小写、文件名全大写。
# 改造页默认落在「强化」标签，因此用它作为页面身份。
INTENSIFY_TAB_TEMPLATE = 'INTENSIFY_TAB_720P.png'
REMOLD_TAB_TEMPLATE = 'INTENSIFY_REMOLD_TAB_720P.png'
SKILL_TAB_TEMPLATE = 'INTENSIFY_SKILL_TAB_720P.png'


# ── 改造页面识别区域 ────────────────────────────────────────────────────────

# 改造页三个标签的归一化区域，校准基准为 1280x720 截图。
INTENSIFY_TAB_ROI = ROI(0.15, 0.0167, 0.218, 0.0792)
REMOLD_TAB_ROI = ROI(0.2782, 0.0195, 0.3461, 0.0778)
SKILL_TAB_ROI = ROI(0.4086, 0.0139, 0.4735, 0.0778)


# ── 改造页面导航落点 ────────────────────────────────────────────────────────

# 左上角返回按钮；强化页与出征页、好友页、建造页的返回按钮落在同一位置。
CLICK_BACK = (0.0219, 0.0584)


# ── 改造页面标签落点 ────────────────────────────────────────────────────────

# 坐标为 1280x720 参考画面的归一化值，取自激活标签模板的中心；键与标签名一致。
TAB_POSITIONS: dict[str, tuple[float, float]] = {
    'intensify': (0.1836, 0.0472),  # 顶部强化标签，用于进入舰船强化内容。
    'remold': (0.3117, 0.0479),  # 顶部改造标签，用于进入舰船改造内容。
    'skill': (0.4406, 0.0451),  # 顶部技能标签，用于进入技能内容。
}


__all__ = [
    'CLICK_BACK',
    'INTENSIFY_TAB_ROI',
    'INTENSIFY_TAB_TEMPLATE',
    'REMOLD_TAB_ROI',
    'REMOLD_TAB_TEMPLATE',
    'SKILL_TAB_ROI',
    'SKILL_TAB_TEMPLATE',
    'TAB_POSITIONS',
    'TEMPLATE_NAMESPACE',
]
