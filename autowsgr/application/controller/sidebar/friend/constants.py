"""模块功能：好友页面的识别数据与点击落点。

上层调用：
- autowsgr.application.controller.sidebar.friend.checker：读取模板名与识别区域。
- autowsgr.application.controller.sidebar.friend.page：读取点击落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间：好友从侧边栏进入，因此嵌在 sidebar 命名空间下。
TEMPLATE_NAMESPACE = 'controller/sidebar/friend'

# 本模块的模板文件名；目录小写、文件名全大写。
# 好友页面有两个页签，账号设置不同进入后停留的页签也不同，两个都要认。
FRIEND_TAB_TEMPLATE = 'FRIEND_TAB_720P.png'
FRIEND_ADD_TAB_TEMPLATE = 'FRIEND_ADD_TAB_720P.png'


# ── 好友页面识别区域 ────────────────────────────────────────────────────────

# 两个页签各自的归一化区域，校准基准为 1280x720 截图。
# 尺寸都比对应模板大 1px 以上，避免换算截断后区域小于模板。
# 「好友」页签（模板 86x46，区域 88x48）。
FRIEND_TAB_ROI = ROI(0.1484, 0.0139, 0.2172, 0.0806)
# 「添加」页签（模板 94x42，区域 96x44）。
FRIEND_ADD_TAB_ROI = ROI(0.4016, 0.0194, 0.4766, 0.0806)


# ── 好友页面导航落点 ────────────────────────────────────────────────────────

# 左上角返回按钮；好友与出征页的返回按钮落在同一位置，因此共用同一坐标。
CLICK_BACK = (0.0219, 0.0584)


# ── 好友页面标签落点 ────────────────────────────────────────────────────────

# 好友页只有「好友」一个标签，取其激活模板中心，用于切回该标签。
CLICK_TAB = (0.1828, 0.0472)


__all__ = [
    'CLICK_BACK',
    'CLICK_TAB',
    'FRIEND_ADD_TAB_ROI',
    'FRIEND_ADD_TAB_TEMPLATE',
    'FRIEND_TAB_ROI',
    'FRIEND_TAB_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
