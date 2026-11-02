"""模块功能：定义导航器的页面名与导航错误。

上层调用：
- application.navigation 与各 UI 控制器：用 PageName 表达目标页面。
- dispatch.startup：捕获 ManualUpdateRequiredError 转成人工处理错误。

下层依赖：
- common.system.enums：提供字符串枚举基类。
- common.system.errors：提供应用错误基类。

边界：只定义页面名、导航契约与错误类型，不含导航逻辑、识别或点击；
它必须保持零运行时依赖，供所有层级（含下层控制器）导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.common.system.enums import StrEnum
from autowsgr.common.system.errors import ApplicationError


if TYPE_CHECKING:
    from collections.abc import Callable


class PageName(StrEnum):
    """游戏页面名称。"""

    LOGIN_PAGE = '登录页面'
    SERVER_SELECT = '区服选择页面'
    HOME = '主页面'
    HOME_NEWS = '每日公告弹窗'
    HOME_REWARD = '每日奖励弹窗'
    HOME_REWARD_CONFIRM = '每日奖励确认'
    SORTIE_MAP = '出征页面'
    EXERCISE = '演习页面'
    EXERCISE_RIVAL_CONFIRM = '演习对手浮窗'
    EXPEDITION = '远征页面'
    CAMPAIGN = '战役页面'
    BATTLE_PREPARATION = '出征准备'
    DECISIVE_BATTLE_PREPARATION = '决战准备'
    EXERCISE_PREPARATION = '演习准备'
    CAMPAIGN_PREPARATION = '战役准备'
    SIDEBAR = '侧边栏'
    MISSION = '任务页面'
    MISSION_REWARD_CONFIRM = '任务奖励确认'
    BACKYARD = '后院页面'
    ACADEMY = '学院页面'
    BATH = '浴室页面'
    CANTEEN = '食堂页面'
    RANK_ROOM = '军阶室页面'
    RANK_SKILL_LIST = '军阶室技能列表'
    BUILD = '建造页面'
    BUILD_SUBMENU = '建造二级菜单'
    INTENSIFY = '强化页面'
    INTENSIFY_SUBMENU = '强化二级菜单'
    FRIEND = '好友页面'
    DECISIVE_BATTLE = '决战页面'
    SHIP_SELECTION = '选择舰船页面'
    EVENT_MAP = '活动页面'
    EVENT_STAGE_OVERLAY = '活动章节浮窗'


@dataclass(frozen=True, slots=True)
class NavTarget:
    """从某个页面可以直达的一个目标。

    Attributes:
        target: 目标页面。
        action: 执行一次点击的动作，可接收调用方透传的参数。
        description: 这条边的说明，供维护与日志使用。
        confirm: 到达后是否需要确认；浮窗链的中间步判不了"到没到"，置假跳过。
        tab: 到达后要落到的页面内标签；进入这一页会停在别的标签时用它
            （如远征可收时进出征页会自动停在远征）。缺省表示不需要强制切换。
    """

    target: PageName
    action: Callable[..., None]
    description: str = ''
    confirm: bool = True
    tab: str | None = None


@dataclass(frozen=True, slots=True)
class NavTab:
    """页面内的一个标签：怎么点、怎么确认。

    标签不是页面，不参与路径计算；它只描述"到达这一页之后要落在哪个视图上"。
    执行器在到达确认处用这里的 checker 替换页面级确认。

    Attributes:
        click: 点击该标签的动作。
        checker: 判该标签是否激活的确认入口。
        description: 标签说明，供维护与日志使用。
    """

    click: Callable[..., None]
    checker: Callable[..., bool]
    description: str = ''


class NavigationError(ApplicationError):
    """导航失败时抛出。"""


class ManualUpdateRequiredError(NavigationError):
    """游戏需要更新，导航无法继续。

    这不是导航失败：重启游戏也不会改变，应由处理器转成需要人工介入的错误。
    """


__all__ = [
    'ManualUpdateRequiredError',
    'NavTab',
    'NavTarget',
    'NavigationError',
    'PageName',
]
