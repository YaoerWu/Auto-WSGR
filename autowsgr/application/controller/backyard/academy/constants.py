"""模块功能：academy 二级页的识别数据。

上层调用：
- application.controller.backyard.academy.checker：读取识别区域与模板名。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域与模板名等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# UI 模板根下的命名空间：二级页模板放在以页面命名的子目录里。
TEMPLATE_NAMESPACE = 'controller/backyard/academy'

# 模板文件名；目录与命名空间已表达域，文件名不再重复域前缀。
PAGE_TEMPLATE = 'ACADEMY_PAGE_720P.png'

# 学院二级页页面身份的归一化区域，校准基准为 1280x720 截图。
PAGE_ROI = ROI(0.8508, 0.0181, 0.9969, 0.1028)


__all__ = [
    'PAGE_ROI',
    'PAGE_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
