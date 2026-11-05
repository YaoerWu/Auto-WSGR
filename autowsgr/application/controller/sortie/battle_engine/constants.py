"""模块功能：战斗内点击坐标、等待时间与识别模板路径。

上层调用：
- controller.sortie.battle_engine.page：按点击动作取坐标与固定等待时间。
- controller.sortie.battle_engine.monitor：按模板键取模板路径。

下层依赖：
- 无。

边界：只保存不容易变的坐标、等待时间和模板路径；识别判据归 monitor，
地图校准归 tracking。
"""

from __future__ import annotations


# ── 点击坐标（归一化，基准分辨率 1280x720）─────────────────────────────────

CLICK_RETREAT = (0.705, 0.911)
"""索敌成功界面：撤退按钮。"""

CLICK_ENTER_FIGHT = (0.891, 0.928)
"""索敌成功界面：进入战斗按钮。"""

CLICK_PROCEED_YES = (0.339, 0.648)
"""节点推进对话框：继续前进。"""

CLICK_PROCEED_NO = (0.641, 0.648)
"""节点推进对话框：返回港口。"""

CLICK_NIGHT_YES = (0.339, 0.648)
"""夜战对话框：追击。"""

CLICK_NIGHT_NO = (0.641, 0.648)
"""夜战对话框：撤退。"""

CLICK_RESULT_CONTINUE = (0.953, 0.954)
"""战果页面：继续。"""

CLICK_SPEED_UP_NORMAL = (0.260, 0.963)
"""常规战：加速。"""

CLICK_SPEED_UP_BATTLE = (0.396, 0.963)
"""战役与导弹动画：加速。"""

CLICK_FLAGSHIP_CONFIRM = (0.500, 0.500)
"""旗舰大破提示：确认。"""

# ── 等待时间（秒）──────────────────────────────────────────────────────────

CLICK_SETTLE_SECONDS = 0.2
"""普通点击后的稳定等待。"""

ENTER_FIGHT_SETTLE_SECONDS = 0.5
"""点击进入战斗前的等待。"""

FORMATION_SETTLE_SECONDS = 2.0
"""选择阵型后的等待。"""

SPEED_UP_SETTLE_SECONDS = 0.05
"""加速点击前的极短等待。"""

CONFIRM_SETTLE_SECONDS = 0.25
"""资源确认弹窗出现后的等待。"""

CONFIRM_CLOSE_SECONDS = 1.0
"""点掉资源确认弹窗后的等待。"""

# ── 识别模板（相对 resources/image）───────────────────────────────────────

PHASE_TEMPLATES = {
    'battle_times_exceed': 'combat/battle_times_exceed_540p.png',
    'bypass': 'combat/bypass_540p.png',
    'end_battle_page': 'combat/end_battle_page_540p.png',
    'end_exercise_page': 'combat/end_exercise_page_540p.png',
    'end_map_page': 'combat/end_map_page_540p.png',
    'fight_condition': 'combat/fight_condition_540p.png',
    'fight_period': 'combat/fight_period_540p.png',
    'flagship_damage': 'combat/flagship_damage_540p.png',
    'formation': 'combat/formation_540p.png',
    'get_item': 'combat/get_item_540p.png',
    'get_ship': 'combat/get_ship_540p.png',
    'missile_animation': 'combat/missile_animation_540p.png',
    'missile_support': 'combat/missile_support_540p.png',
    'mvp_badge': 'combat/mvp_badge_540p.png',
    'night_battle': 'combat/night_battle_540p.png',
    'proceed': 'combat/proceed_540p.png',
    'result_page': 'combat/result_page_540p.png',
    'spot_enemy': 'combat/spot_enemy_540p.png',
}
"""战斗阶段识别用到的模板相对路径。"""

CONFIRM_TEMPLATE = 'shared/confirm_1_540p.png'
"""资源确认弹窗。"""

RESULT_GRADE_TEMPLATES = {
    'SS': 'combat/result/ss_540p.png',
    'S': 'combat/result/s_540p.png',
    'A': 'combat/result/a_540p.png',
    'B': 'combat/result/b_540p.png',
    'C': 'combat/result/c_540p.png',
    'D': 'combat/result/d_540p.png',
}
"""战果等级图标，顺序即判定优先级。"""


__all__ = [
    'CLICK_ENTER_FIGHT',
    'CLICK_FLAGSHIP_CONFIRM',
    'CLICK_NIGHT_NO',
    'CLICK_NIGHT_YES',
    'CLICK_PROCEED_NO',
    'CLICK_PROCEED_YES',
    'CLICK_RESULT_CONTINUE',
    'CLICK_RETREAT',
    'CLICK_SETTLE_SECONDS',
    'CLICK_SPEED_UP_BATTLE',
    'CLICK_SPEED_UP_NORMAL',
    'CONFIRM_CLOSE_SECONDS',
    'CONFIRM_SETTLE_SECONDS',
    'CONFIRM_TEMPLATE',
    'ENTER_FIGHT_SETTLE_SECONDS',
    'FORMATION_SETTLE_SECONDS',
    'PHASE_TEMPLATES',
    'RESULT_GRADE_TEMPLATES',
    'SPEED_UP_SETTLE_SECONDS',
]
