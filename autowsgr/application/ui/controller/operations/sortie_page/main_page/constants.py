"""模块功能：保存 sortie_page 页面壳和顶部标签的私有物理校准。

上层调用：
- application.ui.controller.operations.sortie_page.main_page.page：执行页面识别、标签切换和返回主页。

下层依赖：
- common.vision：提供颜色值构造。

本模块只保存 sortie_page 页面壳使用的点击坐标、通知探针和颜色容差；章节、地图、
远征槽位等具体页面校准由对应页面目录负责。
"""

from __future__ import annotations

from autowsgr.common.vision.adapters.pixel_matching import Color, PixelRule, PixelSignature


# ── 页面壳和顶部标签 ────────────────────────────────────────────────────────

CLICK_BACK = (0.0219, 0.0584)  # 出征区域左上角返回按钮，用于离开 sortie_page 回到 Home。
TAB_POSITIONS = {
    'sortie': (0.1844, 0.0514),  # 出征标签，用于打开普通出征章节页面。
    'exercise': (0.3157, 0.0500),  # 演习标签，用于打开演习对手页面。
    'expedition': (0.4422, 0.0514),  # 远征标签，用于打开远征收取页面。
    'campaign': (0.5750, 0.0459),  # 战役标签，用于打开战役选择页面。
    'decisive': (0.6985, 0.0514),  # 决战标签，用于打开决战入口页面。
}  # sortie_page 顶部标签点击坐标。


# ── 出征区域远征通知 ────────────────────────────────────────────────────────

# 顶部远征完成通知的像素规则：探针位置命中橙红色即视为通知出现。
EXPEDITION_NOTIF_SIGNATURE = PixelSignature(
    name='expedition_notification',
    rules=(PixelRule(x=0.4953, y=0.0213, color=Color(245, 88, 47), tolerance=40.0),),
)
