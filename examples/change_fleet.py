"""最小示例 — 修改舰队。

修改第 2 舰队的舰船配置。
"""

from autowsgr.application.ui.controller.fleet import BattlePreparationPage
from autowsgr.application.navigation import goto_page
from autowsgr.business.combat.fleet import exact_fleet_rules
from autowsgr.common.types import PageName
from autowsgr.dispatch.legacy_scheduler import launch


# 1. 启动 (加载配置 → 连接模拟器 → 启动游戏)
ctx = launch('usersettings.yaml')

goto_page(ctx, PageName.BATTLE_PREPARATION)

page = BattlePreparationPage(ctx)

page.adjust_fleet(
    fleet_id=2,
    fleet_rules=exact_fleet_rules(['U-47', 'U-96']),
)
