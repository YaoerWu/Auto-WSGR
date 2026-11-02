"""模块功能：维护换船流程的等待与重试参数。

上层调用：
- fleet_select.alignment：控制换船、清空和拖拽后的页面同步节奏。
- fleet_select.battle_preparation.normal：控制最终校验失败后的局部修正次数。

下层依赖：
- 无。

本文件只保存换船流程共享的静态参数，不保存运行时状态。
"""

from __future__ import annotations


# ── 换船流程参数 ────────────────────────────────────────────────────────────

MAX_SET_RETRIES = 2  # 编队最终校验失败后允许的局部修正次数。
MAX_ALIGN_STEPS = 48  # 一轮成员集合调整允许的最大换船动作次数。
SHIP_FUZZY_THRESHOLD = 2  # 准备页舰名在完整舰名表里允许的最大编辑距离。
CONTEXT_MATCH_THRESHOLD = 3  # 舰名在目标池里补救匹配时允许的最大编辑距离。
ACTION_WAIT = 0.3  # 单次换船或清空动作后等待准备页同步的时间。
FLEET_SWITCH_WAIT = 0.5  # 切换准备页舰队后等待舰船卡片刷新的时间。
RETRY_WAIT = 0.5  # 一轮编队校验失败后等待下一次截图的时间。
REORDER_WAIT = 0.5  # 一次拖拽排序后等待槽位顺序稳定的时间。


__all__ = [
    'ACTION_WAIT',
    'CONTEXT_MATCH_THRESHOLD',
    'FLEET_SWITCH_WAIT',
    'MAX_ALIGN_STEPS',
    'MAX_SET_RETRIES',
    'REORDER_WAIT',
    'RETRY_WAIT',
    'SHIP_FUZZY_THRESHOLD',
]
