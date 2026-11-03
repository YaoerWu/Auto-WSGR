"""模块功能：rank_room 二级页的识别数据。

上层调用：
- application.controller.backyard.rank_room.checker：读取识别区域与模板名。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域与模板名等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# UI 模板根下的命名空间：二级页模板放在以页面命名的子目录里。
TEMPLATE_NAMESPACE = 'controller/backyard/rank_room'

# 模板文件名；目录与命名空间已表达域，文件名不再重复域前缀。
PAGE_TEMPLATE = 'RANK_ROOM_PAGE_720P.png'

# 军阶室二级页页面身份的归一化区域，校准基准为 1280x720 截图。
PAGE_ROI = ROI(0.1571, 0.5, 0.3047, 0.5959)


# ── 点击落点 ────────────────────────────────────────────────────────────────

# 技能列表入口，进入三级页。
CLICK_RANK_SKILL_LIST = (0.2301, 0.5465)

__all__ = [
    'CLICK_RANK_SKILL_LIST',
    'PAGE_ROI',
    'PAGE_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
