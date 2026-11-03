"""模块功能：登录流程的识别数据与点击落点。

上层调用：
- application.controller.login.checker：读取模板名、识别区域与 OCR 期望文本。
- application.controller.login.page：读取进入游戏、换区入口与区服条目落点。

下层依赖：
- common.vision：提供识别区域类型。

边界：只保存识别区域、模板名、期望文本与点击落点等静态校准数据，不识别画面、不编排流程、不持有运行状态。
"""

from __future__ import annotations

from autowsgr.common.vision import ROI


# ── 识别模板 ────────────────────────────────────────────────────────────────

# 模板目录名，对应 resources/image/application/controller/login/。
TEMPLATE_NAMESPACE = 'controller/login'

# 健康游戏提示的黑屏画面，全屏模板。
BLACK_SCREEN_TEMPLATE = 'LOGIN_BLACK_SCREEN_720P.png'

# 登录页的进入游戏按钮。
ENTER_BUTTON_TEMPLATE = 'LOGIN_ENTER_BUTTON_720P.png'

# 登录页的点击换区文字。
SWITCH_ENTRY_TEMPLATE = 'SERVER_SWITCH_ENTRY_720P.png'

# 区服选择页的切换大区按钮。
SWITCH_SERVER_TEMPLATE = 'SERVER_SWITCH_BUTTON_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 更新提示文字区域。
UPDATE_PROMPT_ROI = ROI(0.3211, 0.3681, 0.4859, 0.4222)

# 更新中与加载中的进度文字区域，两个画面共用同一条横幅。
PROGRESS_TEXT_ROI = ROI(0.3867, 0.8389, 0.6125, 0.8986)

# 进入游戏按钮区域。
ENTER_BUTTON_ROI = ROI(0.8195, 0.8236, 0.9532, 0.9098)

# 点击换区文字区域。
SWITCH_ENTRY_ROI = ROI(0.6820, 0.6958, 0.7844, 0.7653)

# 切换大区按钮区域。
SWITCH_SERVER_ROI = ROI(0.8133, 0.8792, 0.9407, 0.9667)

# 四个区服条目区域，顺序与区服列表从上到下一致。
SERVER_NAME_ROIS = (
    ROI(0.7836, 0.0389, 0.8984, 0.1194),
    ROI(0.7852, 0.1972, 0.8961, 0.2708),
    ROI(0.7883, 0.3583, 0.8977, 0.4292),
    ROI(0.7867, 0.5097, 0.9000, 0.5847),
)


# ── OCR 期望文本 ────────────────────────────────────────────────────────────

UPDATE_PROMPT_TEXT = '有新的内容需要更新'
LOADING_TEXT = '正在进入港区'
SERVER_NAMES = ('胡德', '俾斯麦', '昆西', '长春')


# ── 登录页落点 ──────────────────────────────────────────────────────────────

# 进入游戏按钮中心，取自识别模板 LOGIN_ENTER_BUTTON_720P 的 ROI 中心。
CLICK_ENTER_GAME = (0.8863, 0.8667)

# 换区入口文字中心，取自识别模板 SERVER_SWITCH_ENTRY_720P 的 ROI 中心。
CLICK_SWITCH_ENTRY = (0.7332, 0.7306)


# ── 区服条目落点 ────────────────────────────────────────────────────────────

# 四个区服条目中心，顺序与区服列表从上到下一致：0 胡德 / 1 俾斯麦 / 2 昆西 / 3 长春。
SERVER_POSITIONS = (
    (0.8410, 0.0792),
    (0.8407, 0.2340),
    (0.8430, 0.3938),
    (0.8434, 0.5472),
)


__all__ = [
    'BLACK_SCREEN_TEMPLATE',
    'CLICK_ENTER_GAME',
    'CLICK_SWITCH_ENTRY',
    'ENTER_BUTTON_ROI',
    'ENTER_BUTTON_TEMPLATE',
    'LOADING_TEXT',
    'PROGRESS_TEXT_ROI',
    'SERVER_NAMES',
    'SERVER_NAME_ROIS',
    'SERVER_POSITIONS',
    'SWITCH_ENTRY_ROI',
    'SWITCH_ENTRY_TEMPLATE',
    'SWITCH_SERVER_ROI',
    'SWITCH_SERVER_TEMPLATE',
    'TEMPLATE_NAMESPACE',
    'UPDATE_PROMPT_ROI',
    'UPDATE_PROMPT_TEXT',
]
