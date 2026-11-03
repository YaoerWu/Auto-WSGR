"""模块功能：侧边栏的识别数据与点击落点。

上层调用：
- application.controller.sidebar.checker：读取模板名与识别区域。
- application.controller.sidebar.page：读取一级条目、二级菜单与关闭落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sidebar'

# 本模块的模板文件名；目录小写、文件名全大写。
SIDEBAR_MAIN_TEMPLATE = 'SIDEBAR_MAIN_720P.png'
BUILD_SUBMENU_TEMPLATE = 'SIDEBAR_BUILD_720P.png'
INTENSIFY_SUBMENU_TEMPLATE = 'SIDEBAR_INTENSIFY_720P.png'


# ── 侧边栏识别区域 ──────────────────────────────────────────────────────────

# 侧边栏展开时「改造」条目的归一化区域，校准基准为 1280x720 截图。
SIDEBAR_MAIN_ROI = ROI(0.118, 0.4694, 0.2453, 0.5306)


# ── 二级菜单识别区域 ────────────────────────────────────────────────────────

# 点「建造」「改造」后右侧弹出的二级菜单首项区域，同一校准基准。
BUILD_SUBMENU_ROI = ROI(0.3024, 0.332, 0.475, 0.407)
INTENSIFY_SUBMENU_ROI = ROI(0.3024, 0.4612, 0.4719, 0.5375)


# ── 侧边栏导航落点 ──────────────────────────────────────────────────────────

# 坐标为 1280x720 参考画面的归一化值，取样自一级条目红框中心；键与 SidebarTarget 枚举名一致。
NAV_POSITIONS = {
    'build': (0.1437, 0.3701),
    'intensify': (0.1434, 0.5000),
    'friend': (0.1426, 0.7549),
}


# ── 二级菜单落点 ────────────────────────────────────────────────────────────

# 点一级条目后右侧弹出二级菜单，这里只登记「首项」——首项才是我们要进的页面：
# 建造菜单的第二项是「特别船坞」、改造菜单的第二项是「工程局」，都不做，不要点。
# 键与 SidebarTarget 枚举名一致；取值来自二级菜单首项识别模板的红框中心。
SUBMENU_POSITIONS: dict[str, tuple[float, float]] = {
    'build': (0.3875, 0.3674),  # 首项「建造」，进入建造页。
    'intensify': (0.3859, 0.4972),  # 首项「改造」，进入改造页。
}


# ── 侧边栏关闭落点 ──────────────────────────────────────────────────────────

# 侧边栏只占屏幕左侧，点中部空白处即可收起；此处避开所有可点对象，不会误触。
CLICK_CLOSE = (0.5391, 0.5000)


__all__ = [
    'BUILD_SUBMENU_ROI',
    'BUILD_SUBMENU_TEMPLATE',
    'CLICK_CLOSE',
    'INTENSIFY_SUBMENU_ROI',
    'INTENSIFY_SUBMENU_TEMPLATE',
    'NAV_POSITIONS',
    'SIDEBAR_MAIN_ROI',
    'SIDEBAR_MAIN_TEMPLATE',
    'SUBMENU_POSITIONS',
    'TEMPLATE_NAMESPACE',
]
