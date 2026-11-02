"""模块功能：按路径逐边执行导航，并在每跳两端做前后识别。

上层调用：
- application.ui.navigation.service：把算好的路径交给执行器走出去。

下层依赖：
- navigation.registry：查询页面的到达确认入口。
- navigation.types：页面契约与导航错误。
- dispatch.session：进程级导航栈。

边界：只执行「已经算好的路径」；不算路、不做入口判断、不处理每日浮窗。
传了 tab 参数时，最后一跳改用该标签的 checker 做到达确认（见 §标签）。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from autowsgr.application.ui.navigation import registry
from autowsgr.application.ui.navigation.types import NavigationError, PageName
from autowsgr.common.system.logger import get_logger


_log = get_logger('ui.navigation.executor')


# 全层扫描是「试问」：一次要问遍所有页面，绝大多数不会命中。识别细节与各检查器的
# 读事实日志在扫描期间整体静默，只由调用方保留一条汇总。
_QUIET_DURING_PROBE = (
    'autowsgr.common.vision',
    'autowsgr.application.controller',
)


# ── 页面内标签参数 ──────────────────────────────────────────────────────────

# 点页面入口后页面本身还在切换动画里，此时点标签会落空；先等它稳定再点、再验。
# 到达首页或侧边栏后，浮窗可能延迟弹出；先停一会儿再记账。
_ARRIVAL_SETTLE_SECONDS = 3.0

# 动作点下去之后画面还在切换，这段时间里域探针读到的是旧页。先等稳定再读一帧，
# 域探针一帧就能判完整族页面，不需要扫全层确认「当前层是谁」。
_DOMAIN_ARRIVAL_SETTLE_SECONDS = 2.0

# 「到达」只说明目标页的标志已经出现在画面里，入场动画往往还没走完；这段动画期间
# 的触摸会被游戏丢掉。留一段稳定窗口，让调用方拿到页面时它是真的可点的。
_ARRIVAL_REST_SECONDS = 1.2

_TAB_SETTLE_SECONDS = 2.0

# 标签栏要等页面入场动画结束才属于「这一页」；动画期间点下去会落在上一页。
# 所以点完必须验证，没切过去就再点一次——目标标签已经激活时重复点击不改变状态。
_TAB_CLICK_ATTEMPTS = 2
_TAB_RETRY_INTERVAL_SECONDS = 2.0


if TYPE_CHECKING:
    from autowsgr.application.ui.navigation.types import NavTarget
    from autowsgr.dispatch.context import ContextHandle
    from autowsgr.dispatch.session import SessionState


class NavigationExecutor:
    """逐边执行一条导航路径，并在每跳两端自动做前后识别。

    一次点击的语义天然是成对的：旧页面的标志应当消失（后识别），新页面的标志应当
    出现（前识别）。执行器同时掌握「离开谁」（压栈前的栈顶）与「去往谁」
    （边的目标），因此这个判断由它统一负责，边与 checker 都不需要各自声明。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        session: 进程级导航会话状态。
        checkpoint: 是否在断点查让路信号。终止收尾那一趟必须关掉，否则停止开关
            还亮着，导航会立刻再抛一次。
    """

    def __init__(
        self, ctx: ContextHandle, session: SessionState, *, checkpoint: bool = True
    ) -> None:
        """绑定任务上下文与导航会话状态。"""
        self._ctx = ctx
        self._session = session
        self._checkpoint = checkpoint

    # ── 两个方向 ────────────────────────────────────────────────────────────

    def walk_forward(self, path: tuple[NavTarget, ...], params: dict[str, object]) -> None:
        """前进：按路径从当前页走向目标页。

        每跳依次执行：边的动作 → 到达确认 → 记栈；记完立刻过断点。

        Args:
            path: 已经算好的路径。
            params: 透传给边动作的参数（例如活动章节的 node、区服的 position）。

        Raises:
            NavigationError: 到达确认失败。
            TaskPaused: 断点收到暂停或插队信号。
            TaskStopped: 断点收到终止信号。
        """
        # 调用方显式要的标签只落在最后一跳：走到目的地再切，中途切了还得切回来。
        requested = params.get('tab')
        tab = requested if isinstance(requested, str) else None
        self._check_interrupt()
        for index, edge in enumerate(path):
            _log.debug('[UI] 导航执行 → 前进：edge={!r}', edge.description)
            edge.action(self._ctx, **params)
            # 标签跟着这一跳走：边自己声明的是「到达这一页就先切到哪个标签」
            # （如「首页 → 演习页」固定切演习），多跳路径里中间那一跳同样要切。
            target_tab = tab if tab is not None and index == len(path) - 1 else edge.tab
            if target_tab is not None:
                self._enter_tab(edge.target, target_tab)
            else:
                self._confirm_arrival(edge)
            self._record_page(edge.target)
            # 断点放在确认到达并压栈之后：此时回退路径完整，让路不丢位置。
            self._check_interrupt()

    def walk_backward(self, path: tuple[NavTarget, ...]) -> None:
        """后退：按路径从当前页退回上一页。

        与前进的差别只有两点：回退不接受调用方参数；栈的记账由调用方完成
        （`navigate_back` 已经弹掉一层），这里只走路径、点、确认，不再动栈。
        回退一个「锚点」跟路径上有几步无关，所以不能按步数记账。

        Args:
            path: 已经算好的回退路径。

        Raises:
            NavigationError: 到达确认失败。
            TaskPaused: 断点收到暂停或插队信号。
            TaskStopped: 断点收到终止信号。
        """
        for edge in path:
            _log.debug('[UI] 导航执行 → 后退：edge={!r}', edge.description)
            edge.action(self._ctx)
            self._confirm_arrival(edge)
            self._check_interrupt()

    # ── 栈记账 ──────────────────────────────────────────────────────────────

    def _record_page(self, page: PageName) -> None:
        """把刚到达的页面记进导航栈。

        记法由三件事决定：浮窗只是页面里的一层覆盖，不占格；同一域里的页面共用
        一套画面框架，换页只把栈顶换掉；换了域才是真的换了一层画面，压一格。

        Args:
            page: 刚确认到达的页面。
        """
        if registry.is_overlay_page(page):
            return
        current = self._session.current_page()
        if current is None:
            self._session.push_page(page.value)
            return
        current_page = PageName(current)
        if current_page is page:
            return
        # 浮窗不占格，栈顶正常不会是浮窗；真遇上了就顺势换掉，保证栈里只剩页面。
        if registry.is_overlay_page(current_page):
            self._session.replace_page(page.value)
            return
        domain = registry.domain_of(page)
        if domain is None or domain != registry.domain_of(current_page):
            self._session.push_page(page.value)
            return
        self._session.replace_page(page.value)

    # ── 断点 ────────────────────────────────────────────────────────────────

    def _check_interrupt(self) -> None:
        """断点：dispatch 要求让路时抛出，边与边之间是唯一的让路位置。"""
        if self._checkpoint:
            self._ctx.check_interrupt()

    # ── 页面层识别 ──────────────────────────────────────────────────────────

    def detect_layer(
        self,
        *,
        attempts: int = 1,
        interval_seconds: float = 0.2,
    ) -> tuple[PageName, ...]:
        """返回当前命中的全部层，按深度降序（最上面那层在最前）。

        覆盖层（浮窗、侧边栏、二级菜单）总是比被盖住的页面更深，所以命中的页面里
        深度最大的那个就是当前层。**不能命中即停**：深度排序只保证「更深的排在前面」，
        而单个入口可能因为画面过渡或识别偏差给出假阳性，必须拿全部结果再比较。
        返回全部层而不是只返回最上面那层，是为了让调用方能按层级建栈。

        Args:
            attempts: 每个确认入口的识别次数，默认只读一帧。
            interval_seconds: 两次识别之间的等待秒数。

        Returns:
            命中的全部层，按深度降序；一个确认入口都没命中时返回空元组。
        """
        by_depth = sorted(
            (page for page in PageName if registry.get_checker(page) is not None),
            key=registry.depth_of,
            reverse=True,
        )
        hits: list[PageName] = []
        for name in _QUIET_DURING_PROBE:
            logger.disable(name)
        try:
            # 先问域探针：一个域一帧只读一次，避免同组页面重复截图。
            hits.extend(
                registry.probe_domains(
                    self._ctx,
                    attempts=attempts,
                    interval_seconds=interval_seconds,
                ),
            )
            for page in by_depth:
                confirm = registry.get_checker(page)
                if confirm is None:
                    continue
                try:
                    matched = confirm(
                        self._ctx, attempts=attempts, interval_seconds=interval_seconds
                    )
                except Exception:
                    # 某些入口需要任务额外提供上下文（如活动玩法），探测时没有，
                    # 报错就当它不匹配，继续看下一层。
                    matched = False
                if matched:
                    hits.append(page)
        finally:
            for name in _QUIET_DURING_PROBE:
                logger.enable(name)
        if not hits:
            _log.debug('[UI] 导航执行 → 全层扫描：hits=[]，result=未识别到')
            return ()
        ordered = tuple(sorted(hits, key=registry.depth_of, reverse=True))
        _log.debug('[UI] 导航执行 → 全层扫描：hits={!r}', [page.value for page in ordered])
        return ordered

    def read_layers_clearing_overlay(
        self,
        *,
        attempts: int = 1,
        interval_seconds: float = 0.2,
    ) -> tuple[PageName, ...]:
        """扫一帧；顶上若压着浮窗，先清掉再重扫，返回可以直接建栈的页面层。

        浮窗不建栈，冷启动停在浮窗上时栈没有落点，必须先把它清掉；清路的过程本身
        会把下面那层页面记进栈。返回的层由深到浅，浮窗已经滤掉。

        Args:
            attempts: 每个确认入口的识别次数，默认只读一帧。
            interval_seconds: 两次识别之间的等待秒数。

        Returns:
            当前画面上能作栈的页面层，按深度降序；一层都没有时为空元组。
        """
        layers = self.detect_layer(attempts=attempts, interval_seconds=interval_seconds)
        if layers and registry.is_overlay_page(layers[0]):
            # 浮窗下面那层就是它盖住的页面；看不见时（公告整个挡住主页）落到主页。
            underlying = next(
                (page for page in layers[1:] if not registry.is_overlay_page(page)),
                PageName.HOME,
            )
            _log.debug(
                '[UI] 导航执行 → 冷启动停在浮窗上：overlay={!r}，清向={!r}',
                layers[0].value,
                underlying.value,
            )
            self.walk_forward(registry.find_path(layers[0], underlying), {})
            layers = self.detect_layer(attempts=attempts, interval_seconds=interval_seconds)
        return tuple(page for page in layers if not registry.is_overlay_page(page))

    def _enter_tab(self, page: PageName, tab: str) -> None:
        """切到目标页内的标签，并用该标签自己的 checker 确认。

        传了标签时页面级确认不参与：切到别的标签之后，认"默认标签激活"的页面级
        checker 本来就该失败，两者互斥。

        Args:
            page: 刚到达的页面。
            tab: 标签键，见 `registry.get_tabs`。

        Raises:
            NavigationError: 页面没有该标签，或点完标签仍未激活。
        """
        entry = registry.get_tabs(page).get(tab)
        if entry is None:
            raise NavigationError(f'到达确认失败：{page.value!r} 没有标签 {tab!r}')
        switched = False
        for attempt in range(_TAB_CLICK_ATTEMPTS):
            time.sleep(_TAB_SETTLE_SECONDS if attempt == 0 else _TAB_RETRY_INTERVAL_SECONDS)
            entry.click(self._ctx)
            if entry.checker(self._ctx):
                switched = True
                break
        if not switched:
            raise NavigationError(f'标签切换失败：{page.value!r} → {entry.description!r}')
        _log.debug(
            '[UI] 导航执行 → 标签确认：page={!r}，tab={!r}，结果=成功',
            page.value,
            entry.description,
        )

    def _confirm_arrival(self, edge: NavTarget) -> None:
        """到达确认：目标页出现，且它确实在最上面。

        逐页页面先等目标页识别入口命中，再按页面深度扫一遍，确认没有别的覆盖层还盖在
        目标页上面；域页面改问域探针，一帧判完整族，不必扫全层。

        Args:
            edge: 刚执行完的边。

        Raises:
            NavigationError: 目标页没出现，或当前层不是目标页。
        """
        if not edge.confirm:
            _log.debug('[UI] 导航执行 → 到达确认：page={!r}，结果=跳过', edge.target.value)
            return
        # 首页和侧边栏上会弹每日浮窗；标记不齐说明今天还没处理完，先等过弹出动画再判层。
        if edge.target in (PageName.HOME, PageName.SIDEBAR) and not registry.popups_all_settled():
            time.sleep(_ARRIVAL_SETTLE_SECONDS)
        # 域页面由探针一次判完整族：动作刚点下去画面还在切换，先等稳定再读一帧。
        # 探针返回这一帧能同时看到的全部层，只有最深的那个才是当前层——点关闭没关掉时
        # 浮窗和底下的页面会一起命中，按「目标在不在」放行就会误判到达。
        if registry.is_domain_page(edge.target):
            time.sleep(_DOMAIN_ARRIVAL_SETTLE_SECONDS)
            layers = registry.probe_domains(self._ctx)
            current = max(layers, key=registry.depth_of) if layers else None
            if current is not edge.target:
                detail = '未识别到任何页面' if current is None else f'当前层是 {current.value!r}'
                raise NavigationError(f'到达确认失败：{edge.description!r}，{detail}')
            registry.on_arrival(self._ctx, edge.target)
            _log.debug('[UI] 导航执行 → 到达确认：page={!r}，结果=成功', edge.target.value)
            return
        confirm = registry.get_checker(edge.target)
        if confirm is None:
            _log.debug('[UI] 导航执行 → 到达确认：page={!r}，结果=跳过', edge.target.value)
            return
        # 先等目标页出现（它的入口自带重试，负责等切换动画走完）。
        confirm_result = confirm(self._ctx)
        if not confirm_result:
            raise NavigationError(f'到达确认失败：{edge.description!r}')
        # 再确认「当前层就是目标」：目标出现不代表它就在最上面——浮窗、侧边栏
        # 这类覆盖层会盖住它，按深度降序扫一遍就能分辨出真正的当前层。
        layers = self.detect_layer()
        layer = layers[0] if layers else None
        if layer is not edge.target:
            # 一个页面都没认出来同样算异常：扫不到任何层说明识别链路本身出了问题，
            # 不能当成「无法判断所以放行」。
            detail = '未识别到任何页面' if layer is None else f'当前层是 {layer.value!r}'
            raise NavigationError(f'到达确认失败：{edge.description!r}，{detail}')
        registry.on_arrival(self._ctx, edge.target)
        time.sleep(_ARRIVAL_REST_SECONDS)
        _log.debug('[UI] 导航执行 → 到达确认：page={!r}，结果=成功', edge.target.value)


__all__ = ['NavigationExecutor']
