"""模块功能：维护换船流程的等待节奏与扫描次数。

上层调用：
- fleet_select.models：控制最终校验失败后的局部修正次数。
- fleet_select.operation：控制换船、清空、拖拽与船池扫描之间的等待时间。

下层依赖：
- 无。

边界：只保存流程节奏参数，不保存识别文字形态，不保存运行时状态。
"""

from __future__ import annotations


# ── 编队修正 ────────────────────────────────────────────────────────────────

MAX_SET_RETRIES = 2  # 编队最终校验失败后允许的局部修正次数。
MAX_ALIGN_STEPS = 48  # 一轮成员集合调整允许的最大换船动作次数。
MAX_REORDER_STEPS = 12  # 位置对齐最多拖拽几次，每拖一步都会重新识别一次顺序。


# ── 页面同步 ────────────────────────────────────────────────────────────────

ACTION_WAIT = 0.3  # 单次换船或清空动作后等待准备页同步的时间。
FLEET_SWITCH_WAIT = 0.5  # 切换准备页舰队后等待舰船卡片刷新的时间。
RETRY_WAIT = 0.5  # 一轮编队校验失败后等待下一次截图的时间。
REORDER_WAIT = 0.5  # 一次拖拽排序后等待槽位顺序稳定的时间。


# ── 船池扫描 ────────────────────────────────────────────────────────────────

LIST_SCAN_ATTEMPTS = 3  # 每条选船规则最多扫几屏船池列表。
POOL_OPEN_SETTLE_SECONDS = 1.0  # 点开槽位后等待船池滑入动画放完再操作。
SCROLL_SETTLE_SECONDS = 0.5  # 滚动之后给列表回弹留的时间。
CARD_CLICK_SETTLE_SECONDS = 1.0  # 点卡前给卡片选中动画留的时间。
SEARCH_COMMIT_WAIT = 0.6  # 输入舰名后等待输入法上屏再提交搜索的时间。

SEARCH_KEYBOARD_WAIT = 1.0  # 点击搜索框后等待软键盘弹出动画结束的时间。
SEARCH_RESULT_WAIT = 1.0  # 提交搜索后等待船池按名字过滤完成的时间。


__all__ = [
    'ACTION_WAIT',
    'CARD_CLICK_SETTLE_SECONDS',
    'FLEET_SWITCH_WAIT',
    'LIST_SCAN_ATTEMPTS',
    'MAX_ALIGN_STEPS',
    'MAX_REORDER_STEPS',
    'MAX_SET_RETRIES',
    'POOL_OPEN_SETTLE_SECONDS',
    'REORDER_WAIT',
    'RETRY_WAIT',
    'SCROLL_SETTLE_SECONDS',
    'SEARCH_COMMIT_WAIT',
    'SEARCH_KEYBOARD_WAIT',
    'SEARCH_RESULT_WAIT',
]
