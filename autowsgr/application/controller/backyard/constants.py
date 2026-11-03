"""模块功能：后院主页的识别数据与点击落点。

上层调用：
- application.controller.backyard.checker：读取入口模板名与识别区域。
- application.controller.backyard.page：读取入口与返回按钮的点击落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间；四个入口模板都放在这个根目录下。
TEMPLATE_NAMESPACE = 'controller/backyard'


# ── 后院主页身份 ────────────────────────────────────────────────────────────

# 后院主页没有专属模板：四个入口同一时刻出现，任选其一当身份即可，这里取浴室入口。
BACKYARD_TEMPLATE = 'BACKYARD_BATH_ENTRY_720P.png'
BACKYARD_ROI = ROI(0.2446, 0.3, 0.3524, 0.4167)


# ── 四个入口（点击落点用） ──────────────────────────────────────────────────

CANTEEN_ENTRY_TEMPLATE = 'BACKYARD_CANTEEN_ENTRY_720P.png'
ACADEMY_ENTRY_TEMPLATE = 'BACKYARD_ACADEMY_ENTRY_720P.png'
RANK_ROOM_ENTRY_TEMPLATE = 'BACKYARD_RANK_ROOM_ENTRY_720P.png'
BATH_ENTRY_TEMPLATE = 'BACKYARD_BATH_ENTRY_720P.png'

CANTEEN_ENTRY_ROI = ROI(0.7485, 0.5764, 0.8758, 0.7487)
ACADEMY_ENTRY_ROI = ROI(0.8641, 0.3473, 0.9696, 0.4695)
RANK_ROOM_ENTRY_ROI = ROI(0.6493, 0.1514, 0.7532, 0.2362)
BATH_ENTRY_ROI = ROI(0.2446, 0.3, 0.3524, 0.4167)


# ── 后院导航落点 ────────────────────────────────────────────────────────────

# 四个二级页入口的静态兜底落点，取自入口模板红框中心；键与 BackyardTarget 枚举名一致。
# 正常路径的落点由导航器从 checker 读到的模板中心传入，这里是读不到中心时的兜底。
NAV_POSITIONS = {
    'canteen': (0.8117, 0.6618),  # 餐厅入口，进入餐厅二级页。
    'academy': (0.9164, 0.4076),  # 学院入口，进入学院二级页。
    'rank_room': (0.7008, 0.1931),  # 军阶室入口，进入军阶室二级页。
    'bath': (0.2980, 0.3576),  # 浴室入口，进入浴室二级页。
}


# ── 后院页面按钮落点 ────────────────────────────────────────────────────────

# 退回上一级：后院主页按它回主页面，二级页按它回后院主页，两处同位置。
CLICK_BACK = (0.0527, 0.0694)
# 二级页通用回首页按钮，四个二级页共用，直接从二级页回主页面。
CLICK_HOME = (0.1305, 0.0708)


__all__ = [
    'ACADEMY_ENTRY_ROI',
    'ACADEMY_ENTRY_TEMPLATE',
    'BACKYARD_ROI',
    'BACKYARD_TEMPLATE',
    'BATH_ENTRY_ROI',
    'BATH_ENTRY_TEMPLATE',
    'CANTEEN_ENTRY_ROI',
    'CANTEEN_ENTRY_TEMPLATE',
    'CLICK_BACK',
    'CLICK_HOME',
    'NAV_POSITIONS',
    'RANK_ROOM_ENTRY_ROI',
    'RANK_ROOM_ENTRY_TEMPLATE',
    'TEMPLATE_NAMESPACE',
]
