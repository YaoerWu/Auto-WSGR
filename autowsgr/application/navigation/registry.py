"""模块功能：维护页面之间的可达列表、到达确认与边动作。

上层调用：
- application.navigation.service：查询可达目标、到达确认与完整路径。

下层依赖：
- navigation.types：提供页面契约与错误。
- application.controller：提供到达确认入口与一次点击的动作。

边界：维护"能去哪、到了吗"，以及一行数据写不下的那几步——边动作。
边动作只读 checker 的事实、调 controller 点一下、确认后记账，不拼坐标、不写流程。
"""

from __future__ import annotations

import functools
from collections import deque
from typing import TYPE_CHECKING

from autowsgr.application.controller import (
    backyard,
    home,
    login,
    mission,
    sidebar,
)
from autowsgr.application.controller.backyard import (
    BackyardPage,
    BackyardTarget,
)
from autowsgr.application.controller.event import stage_push
from autowsgr.application.controller.home import (
    HomePage,
    Target,
)
from autowsgr.application.controller.login import LoginPage
from autowsgr.application.controller.mission import MissionPage
from autowsgr.application.controller.sidebar import (
    SidebarPage,
    SidebarTarget,
    build,
    intensify,
)
from autowsgr.application.controller.sidebar.build import (
    BuildPage,
    BuildTab,
)
from autowsgr.application.controller.sidebar.friend import FriendPage, check_friend_page
from autowsgr.application.controller.sidebar.intensify import (
    IntensifyPage,
    IntensifyTab,
)
from autowsgr.application.controller.sortie import (
    SortiePage,
    SortieTab,
    exercise,
    read_sortie_layer,
)
from autowsgr.application.controller.sortie.battle import BattlePage, ensure_chapter
from autowsgr.application.controller.sortie.battle_preparation import (
    BattlePreparationPage,
    read_battle_preparation_layer,
)
from autowsgr.application.controller.sortie.battle_preparation.ship_pool import (
    check_ship_pool_page,
)
from autowsgr.application.controller.sortie.exercise import ExercisePage
from autowsgr.application.navigation.types import (
    NavigationError,
    NavTab,
    NavTarget,
    PageName,
)
from autowsgr.application.ui.controller.home.event_page import EventPage
from autowsgr.dispatch.session import DailyPopup, get_session


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.dispatch.context import ContextHandle


# ── 常量 ────────────────────────────────────────────────────────────────────

# 侧边栏展开/收起约 1.5 秒，5 次 x 0.4 秒留余量；领奖确认走网络，给 8 次。
_SIDEBAR_SETTLE_ATTEMPTS = 5
_SIDEBAR_SETTLE_INTERVAL_SECONDS = 0.4
_CLAIM_CONFIRM_ATTEMPTS = 8
# 标签切换有动画，命中即返回。
_SORTIE_TAB_ATTEMPTS = 7
# 不可达页面给负深度，判层时排到可达页面之后。
_UNREACHABLE_DEPTH = -1


# ── 查询入口 ────────────────────────────────────────────────────────────────


def popups_all_settled() -> bool:
    """今天的三个每日浮窗是否都已处理。"""
    return home.popups_all_settled()


def on_arrival(ctx: ContextHandle, page: PageName) -> None:
    """到达某个页面后刷新会话记账。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        page: 刚确认到达的页面。
    """
    if page is PageName.HOME:
        home.mark_popups_settled(ctx)


def get_targets(page: PageName) -> tuple[NavTarget, ...]:
    """返回某个页面可以直达的目标。

    Args:
        page: 起点页面。

    Returns:
        该页面的直达边；没有出边时为空元组。
    """
    return _NAV_TARGETS.get(page, ())


def get_checker(page: PageName) -> Callable[[ContextHandle], bool] | None:
    """返回某个页面的到达确认入口。

    Args:
        page: 目标页面。

    Returns:
        该页面的确认入口；未注册时为 None。
    """
    return _PAGE_CHECKERS.get(page)


def probe_domains(
    ctx: ContextHandle,
    *,
    attempts: int = 1,
    interval_seconds: float = 0.2,
) -> tuple[PageName, ...]:
    """探测所有域，返回本帧命中的页面。

    识别节奏由调用方决定：判层按「试问」只读一帧，等页面切换的重试留给
    执行器，探针自己不额外等待。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 每个域探针的识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        域探针命中的页面；一个都没命中时为空元组。
    """
    hits: list[PageName] = []
    for prober in _DOMAIN_PROBERS:
        hits.extend(prober(ctx, attempts=attempts, interval_seconds=interval_seconds))
    return tuple(hits)


def is_domain_page(page: PageName) -> bool:
    """判断页面是否由域探针负责。

    Args:
        page: 待查询的页面。

    Returns:
        该页面由域探针负责时为真。
    """
    return page in _DOMAIN_PAGES


def domain_of(page: PageName) -> int | None:
    """返回页面所属域的编号。

    同一个域里的页面共用一套画面框架，换页不换框架；跨域才是真的换了一层画面。
    导航栈靠这个分别「替换栈顶」和「压一格」。

    Args:
        page: 待查询的页面。

    Returns:
        域的序号；不属于任何域时为 None。
    """
    for index, (_prober, pages, overlays) in enumerate(_DOMAINS):
        if page in pages or page in overlays:
            return index
    return None


def is_overlay_page(page: PageName) -> bool:
    """判断页面是不是浮窗。

    浮窗是页面里的一层覆盖，不是独立页面，所以不占导航栈。

    Args:
        page: 待查询的页面。

    Returns:
        是浮窗时为真。
    """
    return page in _OVERLAY_PAGES


def get_tabs(page: PageName) -> dict[str, NavTab]:
    """返回某个页面登记过的非默认标签。

    Args:
        page: 页面名称。

    Returns:
        标签键到标签描述的映射；该页面没有标签时为空字典。
    """
    return _TABS.get(page, {})


@functools.cache
def depth_of(page: PageName) -> int:
    """页面在导航图里的深度：从主页出发的最短跳数。

    图写在代码里、运行期不变，所以结果可以跨调用记忆；进程重启后重算，
    值完全一样，没有正确性影响。不可达的页面排在最深处。

    Args:
        page: 待查询的页面。

    Returns:
        最短跳数；主页为 0，不可达返回负值，判层时排在所有可达页面之后。
    """
    try:
        return len(find_path(PageName.HOME, page))
    except NavigationError:
        return _UNREACHABLE_DEPTH


def find_path(
    source: PageName,
    target: PageName,
    *,
    exclude: frozenset[PageName] = frozenset(),
) -> tuple[NavTarget, ...]:
    """在可达列表上广度拼接出从 source 到 target 的路径。

    Args:
        source: 起点页面。
        target: 目标页面。
        exclude: 本次算路不经过的页面；用于跳过已经处理过的每日浮窗，
            让路径改走它们的直连边。

    Returns:
        依次执行的边；起点即目标时返回空元组。

    Raises:
        NavigationError: 没有可达路径。
    """
    if source == target:
        return ()

    queue: deque[tuple[PageName, tuple[NavTarget, ...]]] = deque([(source, ())])
    visited = {source}
    while queue:
        page, path = queue.popleft()
        for edge in get_targets(page):
            if edge.target in visited or edge.target in exclude:
                continue
            next_path = (*path, edge)
            if edge.target == target:
                return next_path
            visited.add(edge.target)
            queue.append((edge.target, next_path))
    raise NavigationError(f'没有从 {source.value!r} 到 {target.value!r} 的可达路径')


# ── 边动作 ──────────────────────────────────────────────────────────────────

# 只有"一行数据写不下"的边才写具名动作；不吃参数的签名写 **_，吃参数的写 **params。


# 每日浮窗：链上每一步都"先问再做"，不在就什么都不做。
def _close_daily_news(ctx: ContextHandle, **_: object) -> None:
    """有每日公告就关掉，没有就什么都不做。

    未勾选「今日不再显示」时先勾上，避免第二天又弹。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    state = home.read_news_overlay(ctx)
    if not state.matched:
        return
    page = HomePage(ctx)
    if state.checked is False:
        page.click_news_checkbox()
        # 勾选有反馈：等它真的勾上再关闭，没勾上就不关，留给下次。
        if not home.check_news_checked(ctx):
            return
    page.click_news_close()
    # 关闭有动画：确认它真的让开了再记标记——记下就意味着后续不再识别这个浮窗。
    if home.read_news_overlay(ctx).matched:
        return
    get_session().mark_popup_settled(DailyPopup.NEWS)


def _settle_to_sidebar(ctx: ContextHandle, **_: object) -> None:
    """清完浮窗后落到侧边栏：已经在侧边栏就不动，还在主页就点入口进去。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    if sidebar.check_sidebar_page(
        ctx,
        attempts=_SIDEBAR_SETTLE_ATTEMPTS,
        interval_seconds=_SIDEBAR_SETTLE_INTERVAL_SECONDS,
    ):
        return
    HomePage(ctx).go_to(Target.SIDEBAR)


def _settle_to_home(ctx: ContextHandle, **_: object) -> None:
    """清完浮窗后回主页：奖励确认浮窗还在就点掉，停在侧边栏就关掉它。

    浮窗盖在主页上时（从任务、出征、后来）这一段什么都不用做，直接确认主页即可。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    _confirm_daily_reward(ctx)
    if sidebar.check_sidebar_page(
        ctx,
        attempts=_SIDEBAR_SETTLE_ATTEMPTS,
        interval_seconds=_SIDEBAR_SETTLE_INTERVAL_SECONDS,
    ):
        SidebarPage(ctx).go_back()
        # 收起同样有动画，等它真的让开再交给到达确认。
        sidebar.check_sidebar_page(
            ctx,
            absent=True,
            attempts=_SIDEBAR_SETTLE_ATTEMPTS,
            interval_seconds=_SIDEBAR_SETTLE_INTERVAL_SECONDS,
        )


def _claim_daily_reward(ctx: ContextHandle, **_: object) -> None:
    """有每日奖励就领取，没有就什么都不做。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    if not home.check_home_reward_overlay(ctx):
        return
    HomePage(ctx).click_reward_claim()
    # 领取后确认浮窗会盖上来，领取按钮仍在画面里；等确认浮窗出现才算领取完成。
    if not home.check_home_reward_confirm(ctx, attempts=_CLAIM_CONFIRM_ATTEMPTS):
        return
    get_session().mark_popup_settled(DailyPopup.REWARD)


def _confirm_daily_reward(ctx: ContextHandle, **_: object) -> None:
    """有奖励确认浮窗就点确认，没有就什么都不做。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    if not home.check_home_reward_confirm(ctx):
        return
    HomePage(ctx).click_reward_confirm()
    # 确认后有动画：确认浮窗真的让开了再记标记。
    if home.check_home_reward_confirm(ctx):
        return
    get_session().mark_popup_settled(DailyPopup.REWARD_CONFIRM)


# 任务
def _claim_all_mission_rewards(ctx: ContextHandle, **_: object) -> None:
    """任务页有「全部领取」就点，没有就什么都不做。

    按钮只在有奖励可领时出现，不遮挡任务页，因此不是页面；
    这一步和浮窗链的每一步一样「先问再做」，避免空点。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    if not mission.check_claim_all_button(ctx):
        return
    MissionPage(ctx).click_claim_all()


# 活动地图
def _event_map_to_overlay(ctx: ContextHandle, **params: object) -> None:
    """把地图切到目标章节的难度，再点开该章节的浮窗。

    普通与困难共用同一批落点，难度不对就会点开"同名但错误的"章节；因此进浮窗之前
    先对齐难度。难度是否切到位由 checker 按导航确认节奏判定，这里不自己配节奏。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        **params: 可选的 `stage`（章节标识，例如 EX7）；缺省取任务绑定的 event_stage。

    Raises:
        NavigationError: 读不到模式按钮中心，或难度没有切到目标值。
    """
    event_type = stage_push.read_event_type(ctx)
    parsed = stage_push.parse_stage(
        str(params['stage']) if 'stage' in params else stage_push.read_event_stage(ctx)
    )

    state = stage_push.read_event_map_state(ctx, event_type=event_type)
    if state.current_mode is not parsed.difficulty:
        center = stage_push.read_mode_button_center(ctx, event_type=event_type)
        if center is None:
            raise NavigationError('切换活动难度失败：读不到模式按钮中心')
        EventPage(ctx, event_type=event_type).switch_difficulty(center)
        if not stage_push.wait_event_mode(ctx, event_type=event_type, mode=parsed.difficulty):
            raise NavigationError(f'切换活动难度失败：未切到 {parsed.difficulty.value!r}')

    EventPage(ctx, event_type=event_type).go_to_overlay(parsed.node)


# 出征
def _sortie_map_to_preparation(ctx: ContextHandle, **params: object) -> None:
    """按入参选章选节，再点开该节的出征准备页。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        **params: 必填的 chapter（章节）与 map_id（地图节点）。

    Raises:
        ValueError: 缺少章节或地图节点入参。
    """
    chapter = params.get('chapter')
    map_id = params.get('map_id')
    if chapter is None or map_id is None:
        raise ValueError('进入出征准备页需要 chapter 与 map_id 入参')
    ensure_chapter(ctx, chapter=int(chapter), map_id=int(map_id))
    # 选章选节是连续动作，中间不让路；选完、进准备页之前才是安全的断点。
    ctx.check_interrupt()
    BattlePage(ctx).click_enter_sortie()


# 演习
def _exercise_to_rival_overlay(ctx: ContextHandle, **params: object) -> None:
    """打开指定对手的详情浮窗。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        **params: 必填的 rival（对手序号，1-5）。

    Raises:
        ValueError: 缺少对手序号入参。
    """
    rival = params.get('rival')
    if rival is None:
        raise ValueError('打开演习对手浮窗需要 rival 入参')
    ExercisePage(ctx).select_rival(int(rival))


# ── 识别表 ──────────────────────────────────────────────────────────────────

# 一个域一次读一帧：同域页面共享同一组识别数据，逐页读会把同一帧读好几遍。
# 每个探针返回这一帧能同时看到的全部层，由深到浅。一行登记一个域：探针、域内
# 互斥的页面（同一时刻只有一个）、叠在它们上面的浮窗。浮窗和它盖住的页面同域，
# 所以写在同一个域里；区分两者的是第三列，不是「在不在这个域里」。
_DOMAINS: tuple[
    tuple[Callable[..., tuple[PageName, ...]], frozenset[PageName], frozenset[PageName]],
    ...,
] = (
    (
        home.read_home_layer,
        frozenset({PageName.HOME}),
        frozenset(
            {
                PageName.HOME_NEWS,
                PageName.HOME_REWARD,
                PageName.HOME_REWARD_CONFIRM,
            }
        ),
    ),
    (
        read_sortie_layer,
        frozenset(
            {
                PageName.SORTIE_MAP,
                PageName.EXERCISE,
                PageName.EXPEDITION,
                PageName.CAMPAIGN,
                PageName.DECISIVE_BATTLE,
            }
        ),
        frozenset({PageName.EXERCISE_RIVAL_CONFIRM}),
    ),
    (
        read_battle_preparation_layer,
        frozenset(
            {
                PageName.BATTLE_PREPARATION,
                PageName.DECISIVE_BATTLE_PREPARATION,
                PageName.EXERCISE_PREPARATION,
                PageName.CAMPAIGN_PREPARATION,
            }
        ),
        frozenset(),
    ),
)

_DOMAIN_PROBERS: tuple[Callable[..., tuple[PageName, ...]], ...] = tuple(
    prober for prober, _pages, _overlays in _DOMAINS
)

# 由域探针负责的页面（含浮窗）；它们不再登记到逐页注册表。
_DOMAIN_PAGES: frozenset[PageName] = frozenset(
    page for _prober, pages, overlays in _DOMAINS for page in pages | overlays
)


# 浮窗不建栈：它只是页面里的一层覆盖，栈里只记页面本身。冷启动停在浮窗上时，
# 先把它清掉再建栈，栈就自然落在它下面那层。名单由域表第三列算出，不另手写，
# 免得加浮窗时改了一处漏了另一处。
_OVERLAY_PAGES: frozenset[PageName] = frozenset(
    overlay for _prober, _pages, overlays in _DOMAINS for overlay in overlays
)


# 值统一收 (ctx, *, absent=False, ...)：absent=False 判出现，True 判消失。
_PAGE_CHECKERS: dict[PageName, Callable[..., bool]] = {
    PageName.LOGIN_PAGE: login.check_login_page,
    PageName.SERVER_SELECT: login.check_server_select,
    PageName.EVENT_MAP: stage_push.check_event_map_page,
    PageName.EVENT_STAGE_OVERLAY: stage_push.check_event_sortie_prepare,
    PageName.SHIP_SELECTION: check_ship_pool_page,
    PageName.SIDEBAR: sidebar.check_sidebar_page,
    PageName.BUILD_SUBMENU: sidebar.check_build_submenu,
    PageName.INTENSIFY_SUBMENU: sidebar.check_intensify_submenu,
    PageName.BUILD: build.check_build_page,
    PageName.INTENSIFY: intensify.check_intensify_page,
    PageName.FRIEND: check_friend_page,
    PageName.MISSION: mission.check_mission_page,
    PageName.MISSION_REWARD_CONFIRM: mission.check_mission_reward_confirm,
    PageName.BACKYARD: backyard.check_backyard_page,
    PageName.CANTEEN: backyard.check_canteen_page,
    PageName.ACADEMY: backyard.check_academy_page,
    PageName.RANK_ROOM: backyard.check_rank_room_page,
    PageName.BATH: backyard.check_bath_page,
}


# ── 导航表 ──────────────────────────────────────────────────────────────────

# 只登记非默认标签；键与各页面控制器里标签枚举的 name 小写形式一致。
_TABS: dict[PageName, dict[str, NavTab]] = {
    PageName.SORTIE_MAP: {
        # 五个标签互斥，出征虽是默认标签，远征可收时进入会停在远征，因此也登记。
        'sortie': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.SORTIE),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.SORTIE_MAP,)
            ),
            '出征',
        ),
        'exercise': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.EXERCISE),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.EXERCISE,)
            ),
            '演习',
        ),
        'expedition': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.EXPEDITION),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.EXPEDITION,)
            ),
            '远征',
        ),
        'campaign': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.CAMPAIGN),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.CAMPAIGN,)
            ),
            '战役',
        ),
        'decisive': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.DECISIVE),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.DECISIVE_BATTLE,)
            ),
            '决战',
        ),
    },
    # 演习页只有一个前台标签：从首页进来时靠它把顶栏切到演习并确认没有浮窗。
    PageName.EXERCISE: {
        'exercise': NavTab(
            lambda ctx: SortiePage(ctx).go_to(SortieTab.EXERCISE),
            lambda ctx: (
                read_sortie_layer(ctx, attempts=_SORTIE_TAB_ATTEMPTS) == (PageName.EXERCISE,)
            ),
            '演习',
        ),
    },
    PageName.BUILD: {
        'destroy': NavTab(
            lambda ctx: BuildPage(ctx).go_to_tab(BuildTab.DESTROY),
            build.check_dismantle_tab,
            '解体',
        ),
    },
    PageName.INTENSIFY: {
        'remold': NavTab(
            lambda ctx: IntensifyPage(ctx).go_to_tab(IntensifyTab.REMOLD),
            intensify.check_remold_tab,
            '改造',
        ),
        'skill': NavTab(
            lambda ctx: IntensifyPage(ctx).go_to_tab(IntensifyTab.SKILL),
            intensify.check_skill_tab,
            '技能',
        ),
    },
}


# 一条边默认就是一行数据；换页、点一下就走的写 lambda，一行写不下的才写具名动作。
_NAV_TARGETS: dict[PageName, tuple[NavTarget, ...]] = {
    PageName.LOGIN_PAGE: (
        NavTarget(
            PageName.SERVER_SELECT,
            lambda ctx, **_: LoginPage(ctx).click_switch_entry(login.read_switch_entry_center(ctx)),
            '登录页 → 区服选择页',
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: LoginPage(ctx).click_enter_game(login.read_enter_button_center(ctx)),
            '登录页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.SERVER_SELECT: (
        NavTarget(
            PageName.LOGIN_PAGE,
            lambda ctx, **params: LoginPage(ctx).click_server(
                login.read_server_index(ctx, str(params['server']))
            ),
            '区服选择页 → 登录页',
        ),
    ),
    PageName.HOME: (
        NavTarget(
            PageName.SORTIE_MAP,
            lambda ctx, **_: HomePage(ctx).go_to(Target.SORTIE),
            '首页 → 出征页',
            tab='sortie',
        ),
        NavTarget(
            PageName.EXERCISE,
            lambda ctx, **_: HomePage(ctx).go_to(Target.SORTIE),
            '首页 → 演习页',
            tab='exercise',
        ),
        NavTarget(
            PageName.EVENT_MAP,
            lambda ctx, **_: HomePage(ctx).go_to(Target.EVENT),
            '首页 → 活动地图',
        ),
        NavTarget(
            PageName.SIDEBAR,
            lambda ctx, **_: HomePage(ctx).go_to(Target.SIDEBAR),
            '首页 → 侧边栏',
        ),
        NavTarget(
            PageName.MISSION,
            lambda ctx, **_: HomePage(ctx).go_to(Target.TASK),
            '首页 → 任务页',
        ),
        NavTarget(
            PageName.BACKYARD,
            lambda ctx, **_: HomePage(ctx).go_to(Target.BACKYARD),
            '首页 → 后院主页',
        ),
    ),
    PageName.BACKYARD: (
        NavTarget(
            PageName.CANTEEN,
            lambda ctx, **_: BackyardPage(ctx).go_to(
                BackyardTarget.CANTEEN,
                backyard.read_canteen_entry_center(ctx),
            ),
            '后院主页 → 餐厅',
        ),
        NavTarget(
            PageName.ACADEMY,
            lambda ctx, **_: BackyardPage(ctx).go_to(
                BackyardTarget.ACADEMY,
                backyard.read_academy_entry_center(ctx),
            ),
            '后院主页 → 学院',
        ),
        NavTarget(
            PageName.RANK_ROOM,
            lambda ctx, **_: BackyardPage(ctx).go_to(
                BackyardTarget.RANK_ROOM,
                backyard.read_rank_room_entry_center(ctx),
            ),
            '后院主页 → 军阶室',
        ),
        NavTarget(
            PageName.BATH,
            lambda ctx, **_: BackyardPage(ctx).go_to(
                BackyardTarget.BATH,
                backyard.read_bath_entry_center(ctx),
            ),
            '后院主页 → 浴室',
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BackyardPage(ctx).go_back(),
            '后院主页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.CANTEEN: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BackyardPage(ctx).go_home(),
            '餐厅 → 主页（经每日浮窗链）',
            confirm=False,
        ),
        NavTarget(
            PageName.BACKYARD,
            lambda ctx, **_: BackyardPage(ctx).go_back(),
            '餐厅 → 后院主页',
        ),
    ),
    PageName.ACADEMY: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BackyardPage(ctx).go_home(),
            '学院 → 主页（经每日浮窗链）',
            confirm=False,
        ),
        NavTarget(
            PageName.BACKYARD,
            lambda ctx, **_: BackyardPage(ctx).go_back(),
            '学院 → 后院主页',
        ),
    ),
    PageName.RANK_ROOM: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BackyardPage(ctx).go_home(),
            '军阶室 → 主页（经每日浮窗链）',
            confirm=False,
        ),
        NavTarget(
            PageName.BACKYARD,
            lambda ctx, **_: BackyardPage(ctx).go_back(),
            '军阶室 → 后院主页',
        ),
    ),
    PageName.BATH: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BackyardPage(ctx).go_home(),
            '浴室 → 主页（经每日浮窗链）',
            confirm=False,
        ),
        NavTarget(
            PageName.BACKYARD,
            lambda ctx, **_: BackyardPage(ctx).go_back(),
            '浴室 → 后院主页',
        ),
    ),
    PageName.MISSION: (
        NavTarget(
            PageName.MISSION_REWARD_CONFIRM,
            _claim_all_mission_rewards,
            '任务页 → 获得浮窗',
            confirm=False,
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: MissionPage(ctx).go_back(),
            '任务页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.MISSION_REWARD_CONFIRM: (
        NavTarget(
            PageName.MISSION,
            lambda ctx, **_: MissionPage(ctx).click_reward_confirm(),
            '获得浮窗 → 任务页',
        ),
    ),
    # 进侧边栏前当天的浮窗已处理过，回主页点空白处直连，不走浮窗链。
    PageName.SIDEBAR: (
        NavTarget(
            PageName.BUILD_SUBMENU,
            lambda ctx, **_: SidebarPage(ctx).go_to(SidebarTarget.BUILD),
            '侧边栏 → 建造二级菜单',
        ),
        NavTarget(
            PageName.INTENSIFY_SUBMENU,
            lambda ctx, **_: SidebarPage(ctx).go_to(SidebarTarget.INTENSIFY),
            '侧边栏 → 强化二级菜单',
        ),
        NavTarget(
            PageName.FRIEND,
            lambda ctx, **_: SidebarPage(ctx).go_to(SidebarTarget.FRIEND),
            '侧边栏 → 好友页面',
        ),
        NavTarget(
            PageName.HOME,
            lambda ctx, **_: SidebarPage(ctx).go_back(),
            '侧边栏 → 主页面（不经每日浮窗链）',
        ),
    ),
    PageName.BUILD_SUBMENU: (
        NavTarget(
            PageName.BUILD,
            lambda ctx, **_: SidebarPage(ctx).go_to_submenu(SidebarTarget.BUILD),
            '建造二级菜单 → 建造页',
        ),
        NavTarget(
            PageName.HOME,
            lambda ctx, **_: SidebarPage(ctx).go_back(),
            '建造二级菜单 → 主页面（不经每日浮窗链）',
        ),
    ),
    PageName.INTENSIFY_SUBMENU: (
        NavTarget(
            PageName.INTENSIFY,
            lambda ctx, **_: SidebarPage(ctx).go_to_submenu(SidebarTarget.INTENSIFY),
            '强化二级菜单 → 改造页',
        ),
        NavTarget(
            PageName.HOME,
            lambda ctx, **_: SidebarPage(ctx).go_back(),
            '强化二级菜单 → 主页面（不经每日浮窗链）',
        ),
    ),
    PageName.BUILD: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: BuildPage(ctx).go_back(),
            '建造页 → 主页面（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.INTENSIFY: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: IntensifyPage(ctx).go_back(),
            '改造页 → 主页面（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.FRIEND: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: FriendPage(ctx).go_back(),
            '好友页面 → 主页面（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.SORTIE_MAP: (
        NavTarget(
            PageName.BATTLE_PREPARATION,
            _sortie_map_to_preparation,
            '出征页 → 出征准备页',
        ),
        NavTarget(
            PageName.EXERCISE,
            lambda ctx, **_: SortiePage(ctx).go_to(SortieTab.EXERCISE),
            '出征页 → 演习页',
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: SortiePage(ctx).go_back(),
            '出征页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    # 出征四个标签页：进得去就得回得来；标签间怎么切是页内行为，回主页走同一条返回链路。
    PageName.EXERCISE: (
        NavTarget(
            PageName.EXERCISE_RIVAL_CONFIRM,
            _exercise_to_rival_overlay,
            '演习页 → 演习对手浮窗',
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: SortiePage(ctx).go_back(),
            '演习页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.EXPEDITION: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: SortiePage(ctx).go_back(),
            '远征页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.CAMPAIGN: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: SortiePage(ctx).go_back(),
            '战役页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    PageName.DECISIVE_BATTLE: (
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: SortiePage(ctx).go_back(),
            '决战页 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
    # 浮窗上两个出口：关掉回演习页，点挑战进准备页。
    PageName.EXERCISE_RIVAL_CONFIRM: (
        NavTarget(
            PageName.EXERCISE_PREPARATION,
            lambda ctx, **_: ExercisePage(ctx).click_overlay_challenge(
                exercise.read_overlay_challenge_center(ctx)
            ),
            '演习对手浮窗 → 演习准备页',
        ),
        NavTarget(
            PageName.EXERCISE,
            lambda ctx, **_: ExercisePage(ctx).click_overlay_close(
                exercise.read_overlay_close_center(ctx)
            ),
            '演习对手浮窗 → 演习页',
        ),
    ),
    PageName.EXERCISE_PREPARATION: (
        NavTarget(
            PageName.EXERCISE,
            lambda ctx, **_: BattlePreparationPage(ctx).go_back(),
            '演习准备页 → 演习页',
        ),
    ),
    # 只维护退回一条边：选章选节是进入方向的职责，返回不需要入参。
    PageName.BATTLE_PREPARATION: (
        # TODO: 活动出征与普通出征共用这一页的视觉特征，退回固定走出征主页的单条边；
        # 活动入口接上后，从活动进来的退回应改为落到活动地图。影响范围：只这一条边。
        # 删除条件：活动的出征入口登记进 _NAV_TARGETS 时一并改成按参数分叉。
        NavTarget(
            PageName.SORTIE_MAP,
            lambda ctx, **_: BattlePreparationPage(ctx).go_back(),
            '出征准备页 → 出征页',
        ),
    ),
    # 决战与战役准备页还没登记进入方向的边：这两页的入口点击没接，现在只有返回
    # 一条出边，等入口接上即自动生效。
    PageName.DECISIVE_BATTLE_PREPARATION: (
        NavTarget(
            PageName.DECISIVE_BATTLE,
            lambda ctx, **_: BattlePreparationPage(ctx).go_back(),
            '决战准备页 → 决战页',
        ),
    ),
    PageName.CAMPAIGN_PREPARATION: (
        NavTarget(
            PageName.CAMPAIGN,
            lambda ctx, **_: BattlePreparationPage(ctx).go_back(),
            '战役准备页 → 战役页',
        ),
    ),
    # 每日浮窗链：进链只负责走到这一步，中间步的到达确认关掉（下一个浮窗在不在静态判不了），
    # 只有链尾「→ 主页」做真确认。
    PageName.HOME_NEWS: (
        NavTarget(
            PageName.HOME_REWARD,
            _close_daily_news,
            '每日公告 → 每日奖励',
            confirm=False,
        ),
    ),
    PageName.HOME_REWARD: (
        NavTarget(
            PageName.HOME_REWARD_CONFIRM,
            _claim_daily_reward,
            '每日奖励 → 每日奖励确认',
            confirm=False,
        ),
    ),
    # 浮窗可能盖在侧边栏或主页上；清完后落点有两种，已在目标层就什么都不点，避免点错东西。
    PageName.HOME_REWARD_CONFIRM: (
        NavTarget(
            PageName.SIDEBAR,
            _settle_to_sidebar,
            '每日奖励确认 → 侧边栏',
        ),
        NavTarget(
            PageName.HOME,
            _settle_to_home,
            '每日奖励确认 → 主页',
        ),
    ),
    PageName.EVENT_STAGE_OVERLAY: (
        NavTarget(
            PageName.EVENT_MAP,
            lambda ctx, **_: EventPage(
                ctx, event_type=stage_push.read_event_type(ctx)
            ).click_overlay_close(),
            '活动章节浮窗 → 活动地图',
        ),
    ),
    PageName.EVENT_MAP: (
        NavTarget(
            PageName.EVENT_STAGE_OVERLAY,
            _event_map_to_overlay,
            '活动地图 → 章节浮窗',
        ),
        NavTarget(
            PageName.HOME_NEWS,
            lambda ctx, **_: EventPage(ctx, event_type=stage_push.read_event_type(ctx)).go_back(),
            '活动地图 → 主页（经每日浮窗链）',
            confirm=False,
        ),
    ),
}


__all__ = [
    'depth_of',
    'domain_of',
    'find_path',
    'get_checker',
    'get_tabs',
    'get_targets',
    'is_domain_page',
    'is_overlay_page',
    'on_arrival',
    'popups_all_settled',
    'probe_domains',
]
