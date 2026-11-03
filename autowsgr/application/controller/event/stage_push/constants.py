"""模块功能：保存普通推图活动的页面识别数据。

上层调用：
- event.stage_push.checker：读取活动标识、模板名、识别区域与章节期望。

下层依赖：
- common.vision：提供 ROI 类型。

边界：只保存静态校准数据与本期活动期望，不放识别流程。
"""

from __future__ import annotations

import re

from autowsgr.common.vision import ROI


# ── 本期活动识别数据 ────────────────────────────────────────────────────────

# 活动标识与本期期号；换期改期号，并按 <活动>_<期号> 补一份模板目录。
ACTIVITY = 'stage_push'
PERIOD = '20260930'

# 本活动在 UI 模板根下的命名空间：一期一个目录，换期换目录。
TEMPLATE_NAMESPACE = f'controller/event/{ACTIVITY}_{PERIOD}'

# 本活动的模板文件名。
HOME_ENTRY_TEMPLATE = 'EVENT_HOME_ENTRY_720P.png'
MODE_NORMAL_TEMPLATE = 'EVENT_MODE_NORMAL_720P.png'
MODE_HARD_TEMPLATE = 'EVENT_MODE_HARD_720P.png'
SORTIE_PREPARE_TEMPLATE = 'EVENT_SORTIE_PREPARE_720P.png'

# 校准值以 1280x720 截图为基准换算为归一化区域。
HOME_ENTRY_ROI = ROI(0.8546, 0.3222, 0.9883, 0.6834)
# 地图页左下角模式按钮；按钮文字表示"要切换到的"模式，命中它说明当前在另一种难度。
MODE_ROI = ROI(0.0101, 0.9, 0.1118, 0.932)
# 地图标题区域，普通地图与困难地图的名称不同。
MAP_NAME_ROI = ROI(0.4023, 0.0291, 0.5954, 0.0723)
# 节点浮窗内的出击准备按钮，命中即说明节点浮窗已经打开。
SORTIE_PREPARE_ROI = ROI(0.7882, 0.8166, 0.925, 0.882)
# 节点浮窗左上角的关卡标题，干净地图页该区域没有文字。
STAGE_TITLE_ROI = ROI(0.0273, 0.0625, 0.2079, 0.1084)


# ── 本期活动识别期望 ────────────────────────────────────────────────────────

# 地图名与关卡名，换期只改这一段。困难模式的标题在本名后追加"困难"二字；
# 括号形态不稳定，因此不参与比对，只判"标题 + 困难"。
MAP_NAME = '最强之舟'
STAGE_NAMES = {
    1: '天降火雨',
    2: '鹰群出击',
    3: '追逐跳跃',
    4: '火力全开',
    5: '四面合围',
    6: '海空鏖战',
}

# 困难模式的固定标记；实测标题括号有全角、半角和丢失三种形态，因此只判这两个字。
HARD_MARKER = '困难'
# 标题归一化时丢弃的装饰字符，保留数字、字母和汉字。
TITLE_DECORATION = re.compile(r'[^0-9a-zA-Z一-鿿]+')
# 归一化标题里的关卡编号形式，大小写不敏感。
STAGE_TITLE_PATTERN = re.compile(r'ex(\d+)')
# 地图上的落点数量；普通与困难共用同一组落点。
NODE_COUNT = 6


__all__ = [
    'ACTIVITY',
    'HARD_MARKER',
    'HOME_ENTRY_ROI',
    'HOME_ENTRY_TEMPLATE',
    'MAP_NAME',
    'MAP_NAME_ROI',
    'MODE_HARD_TEMPLATE',
    'MODE_NORMAL_TEMPLATE',
    'MODE_ROI',
    'NODE_COUNT',
    'PERIOD',
    'SORTIE_PREPARE_ROI',
    'SORTIE_PREPARE_TEMPLATE',
    'STAGE_NAMES',
    'STAGE_TITLE_PATTERN',
    'STAGE_TITLE_ROI',
    'TEMPLATE_NAMESPACE',
    'TITLE_DECORATION',
]
