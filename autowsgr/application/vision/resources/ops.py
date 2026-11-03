"""业务操作图像模板。

食堂、建造、确认弹窗、错误提示等模板。
所有模板对应 ``autowsgr/common/data/images/`` 下的 PNG 文件。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.vision.resources.combat import CombatTemplates
from autowsgr.dispatch.image_context import LazyTemplate, load_cached_template


if TYPE_CHECKING:
    from autowsgr.common.vision.template import Template


# ═══════════════════════════════════════════════════════════════════════════════
# 分类模板
# ═══════════════════════════════════════════════════════════════════════════════


class Cook:
    """食堂 (做菜) 相关模板。"""

    COOK_BUTTON = LazyTemplate('backyard/canteen_page/cook_button_540p.png', 'cook_button')
    HAVE_COOK = LazyTemplate('backyard/canteen_page/have_cook_540p.png', 'have_cook')
    NO_TIMES = LazyTemplate('backyard/canteen_page/no_times_540p.png', 'no_times')


class GameUI:
    """通用游戏 UI 模板。"""

    REWARD_COLLECT_ALL = LazyTemplate(
        'operations/mission_page/collect_all_540p.png',
        'reward_collect_all',
    )
    REWARD_COLLECT = LazyTemplate(
        'operations/mission_page/collect_540p.png',
        'reward_collect',
    )


class Confirm:
    """确认弹窗模板。"""

    CONFIRM_1 = LazyTemplate('shared/confirm_1_540p.png', 'confirm_1')
    CONFIRM_2 = LazyTemplate('shared/confirm_2_540p.png', 'confirm_2')
    CONFIRM_3 = LazyTemplate('shared/confirm_3_540p.png', 'confirm_3')
    CONFIRM_4 = LazyTemplate('shared/confirm_4_540p.png', 'confirm_4')
    CONFIRM_5 = LazyTemplate('shared/confirm_5_540p.png', 'confirm_5')

    @classmethod
    def all(cls) -> list[Template]:
        """所有确认弹窗模板列表。"""
        return [cls.CONFIRM_1, cls.CONFIRM_2, cls.CONFIRM_3, cls.CONFIRM_4, cls.CONFIRM_5]


class Build:
    """建造相关模板。"""

    # ── 舰船建造 ──
    SHIP_START = LazyTemplate('sidebar/build_page/ship_start_540p.png', 'ship_build_start')
    SHIP_COMPLETE = LazyTemplate('sidebar/build_page/ship_complete_540p.png', 'ship_build_complete')
    SHIP_FAST = LazyTemplate('sidebar/build_page/ship_fast_540p.png', 'ship_build_fast')
    SHIP_FULL_DEPOT = LazyTemplate(
        'sidebar/build_page/ship_full_depot_540p.png',
        'ship_full_depot',
    )

    # ── 装备开发 ──
    EQUIP_START = LazyTemplate('sidebar/build_page/equip_start_540p.png', 'equip_build_start')
    EQUIP_COMPLETE = LazyTemplate(
        'sidebar/build_page/equip_complete_540p.png',
        'equip_build_complete',
    )
    EQUIP_FAST = LazyTemplate('sidebar/build_page/equip_fast_540p.png', 'equip_build_fast')
    EQUIP_FULL_DEPOT = LazyTemplate(
        'sidebar/build_page/equip_full_depot_540p.png',
        'equip_full_depot',
    )

    # ── 资源页面 ──
    RESOURCE = LazyTemplate('sidebar/build_page/resource_540p.png', 'build_resource')


class Fight:
    """战斗相关模板 (ops 侧复用)。"""

    NIGHT_BATTLE = LazyTemplate('combat/night_battle_540p.png', 'night_battle')


FightResult = CombatTemplates.Result


class ChooseShip:
    """选船页面模板。"""

    PAGE_1 = LazyTemplate('fleet/formation/ship_selection/tab_1_540p.png', 'choose_ship_1')
    PAGE_2 = LazyTemplate('fleet/formation/ship_selection/tab_2_540p.png', 'choose_ship_2')
    PAGE_3 = LazyTemplate('fleet/formation/ship_selection/tab_3_540p.png', 'choose_ship_3')
    PAGE_4 = LazyTemplate('fleet/formation/ship_selection/tab_4_540p.png', 'choose_ship_4')


class Symbol:
    """符号/标志模板。"""

    GET_SHIP = LazyTemplate('combat/get_ship_540p.png', 'symbol_get_ship')
    GET_ITEM = LazyTemplate('combat/get_item_540p.png', 'symbol_get_item')
    # MVP 徽章 (result_page_540p): 战果/经验结算页必有且不被遮挡, 比
    # "点击继续" 文字 (result_540p, 被舰船立绘遮挡致分数波动) 稳定
    CLICK_TO_CONTINUE = LazyTemplate('combat/result_page_540p.png', 'click_to_continue')


class BackButton:
    """回退按钮模板。"""

    @staticmethod
    def all() -> list[Template]:
        return [
            load_cached_template(f'shared/back_{i}_540p.png', name=f'back_{i}') for i in range(1, 9)
        ]


class Error:
    """错误/网络问题模板。"""

    BAD_NETWORK_1 = LazyTemplate('runtime/error/bad_network_1_540p.png', 'bad_network_1')
    BAD_NETWORK_2 = LazyTemplate('runtime/error/bad_network_2_540p.png', 'bad_network_2')
    NETWORK_RETRY = LazyTemplate('runtime/error/network_retry_540p.png', 'network_retry')
    REMOTE_LOGIN = LazyTemplate('runtime/error/remote_login_540p.png', 'remote_login')
    REMOTE_LOGIN_CONFIRM = LazyTemplate(
        'runtime/error/remote_login_confirm_540p.png',
        'remote_login_confirm',
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 顶层容器
# ═══════════════════════════════════════════════════════════════════════════════


# 页面/浮层识别模板由 application/ui/controller 页面控制器使用。
class Templates:
    """图像模板统一入口。

    Usage::

        from autowsgr.common.vision._resources import Templates

        Templates.Cook.COOK_BUTTON
        Templates.Build.SHIP_COMPLETE
        Templates.Confirm.all()
    """

    Cook = Cook
    GameUI = GameUI
    Confirm = Confirm
    Build = Build
    Fight = Fight
    FightResult = FightResult
    ChooseShip = ChooseShip
    Symbol = Symbol
    BackButton = BackButton
    Error = Error
