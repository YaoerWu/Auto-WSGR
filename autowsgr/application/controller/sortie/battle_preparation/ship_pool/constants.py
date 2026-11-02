"""模块功能：船池页面的识别数据。

上层调用：
- application.controller.sortie.battle_preparation.ship_pool.checker：读取本模块常量。

下层依赖：
- common.vision：提供识别区域与像素签名类型。

边界：只保存识别区域与页面签名，不保存点击落点、不保存选船规则。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI, Color, PixelRule, PixelSignature


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 船卡列表的正文区，校准基准 1280x720。左边界从 0 起、右边界停在 1048px：
# 再往右是滚动条与右侧信息栏。顶部切掉筛选页签，底部切掉功能按钮栏。
SHIP_LIST_ROI = ROI(0.0, 0.12, 0.81875, 0.95)


# ── 页面签名 ────────────────────────────────────────────────────────────────

# 船池页面的页面签名：右侧信息栏的四段底色与底部一角，五条规则全部命中才成立。
SHIP_POOL_SIGNATURE = PixelSignature(
    'ship_pool_page',
    (
        PixelRule(0.88, 0.24, Color(0, 122, 238)),
        PixelRule(0.86, 0.40, Color(58, 58, 58)),
        PixelRule(0.86, 0.50, Color(59, 59, 59)),
        PixelRule(0.86, 0.70, Color(53, 53, 53)),
        PixelRule(0.98, 0.90, Color(24, 41, 58)),
    ),
)

# 搜索输入态的页面签名：软键盘上排三个键位，三条规则全部命中才成立。
SEARCH_INPUT_SIGNATURE = PixelSignature(
    'ship_pool_input',
    (
        PixelRule(0.3109, 0.9417, Color(253, 253, 253)),
        PixelRule(0.4437, 0.9417, Color(253, 253, 253)),
        PixelRule(0.5883, 0.9347, Color(253, 253, 253)),
    ),
)


__all__ = [
    'SEARCH_INPUT_SIGNATURE',
    'SHIP_LIST_ROI',
    'SHIP_POOL_SIGNATURE',
]
