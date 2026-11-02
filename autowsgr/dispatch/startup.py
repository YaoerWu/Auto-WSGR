"""模块功能：任务开始前的启动与状态编排入口。

上层调用：
- dispatch.processor：派发任务前确保游戏处于「主页 + 浮层已清」。

下层依赖：
- application.navigation：启动段、换区与页面导航都在 UI 层。

边界：只决定何时拉起 App、何时 SL、按配置决定是否换区；不识别画面也不点击，
因此这里不出现任何 checker 调用，识别与点击全部由 UI 层编排。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from autowsgr.application.errors import ManualRepairRequiredError
from autowsgr.application.runtime.types import LoginServer
from autowsgr.application.navigation.service import NavigationService
from autowsgr.application.navigation.types import (
    ManualUpdateRequiredError,
    NavigationError,
    PageName,
)
from autowsgr.common.system.logger import get_logger
from autowsgr.dispatch.session import get_session


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('dispatch.startup')

# 拉起 App 后等进程出现的超时与轮询间隔，单位为秒；进程一出现就立刻往下走。
_APP_PROCESS_TIMEOUT_SECONDS = 30.0
_APP_PROCESS_POLL_SECONDS = 0.5
# 强杀游戏后等待进程退出的时间，单位为秒。
_RESTART_SETTLE_SECONDS = 2.0


def ensure_ready(ctx: ContextHandle, *, allow_restart: bool = True) -> None:
    """确保游戏处于可以开始任务的状态：主页 + 浮层已清。

    幂等：任意状态进来结果一致；SL 与异常恢复复用同一入口。

    Args:
        ctx: 提供设备服务与任务事实的 dispatch 上下文句柄。
        allow_restart: 恢复时是否允许 SL 一次；为假时失败直接抛出。

    Raises:
        ManualRepairRequiredError: 游戏需要更新，只能人工处理，SL 无意义。
        NavigationError: 恢复之后仍然无法回到主页。
    """
    navigator = NavigationService(ctx)

    try:
        _prepare(navigator, ctx)
        navigator.navigate_to(PageName.HOME)
    except ManualUpdateRequiredError as error:
        # 需要更新时重启多少次都一样，不走 SL。
        _log.error('[DISPATCH] 启动 → 终止：reason={!r}', str(error))
        raise ManualRepairRequiredError('检测到游戏更新，请手动完成后重试') from error
    except NavigationError as error:
        if not allow_restart:
            raise
        _log.warning('[DISPATCH] 启动 → 重启：reason={!r}，result=restart', str(error))
        _restart_game(ctx)
        _prepare(navigator, ctx)
        navigator.navigate_to(PageName.HOME)


def _prepare(navigator: NavigationService, ctx: ContextHandle) -> None:
    """把游戏准备到「登录页」，并按用户配置完成换区。

    游戏已经在跑时不做启动段：不知道它停在哪个页面，回主页交给导航器；认不出页面再由
    调用方走 SL。

    Args:
        navigator: 导航器入口。
        ctx: 提供设备服务与任务事实的 dispatch 上下文句柄。

    Raises:
        NavigationError: 启动超时，游戏进程没起来。
    """
    ctrl = ctx.runtime.ctrl
    package = ctx.runtime.config.account.package_name

    cold_started = False
    if not ctrl.check_app_running(package):
        _log.info('[DISPATCH] 启动 → 拉起游戏：package={!r}', package)
        ctrl.start_app(package)
        if not _wait_for_app_process(ctx, package):
            raise NavigationError('启动超时：游戏进程未起来')
        cold_started = True
        # 游戏刚被重新拉起，栈里记的页面已经不存在了。不清空的话接下来那句
        # navigate_to(HOME) 会命中「已在目标页面」而直接短路，实际却还停在启动画面。
        get_session().clear_pages()

    # 多显示器模拟器会把游戏放到独立屏，截图必须跟上，否则识别读的是桌面帧。
    ctrl.follow_display(package)

    if cold_started:
        navigator.navigate_to_login()
        _select_server(navigator, ctx)


def _select_server(navigator: NavigationService, ctx: ContextHandle) -> None:
    """按用户配置完成一次换区；配置为「默认」或本次运行已选过则跳过。

    Args:
        navigator: 导航器入口。
        ctx: 提供设备服务与任务事实的 dispatch 上下文句柄。
    """
    session = get_session()
    if session.server_selected:
        return

    wanted = ctx.runtime.config.account.game_server
    if wanted is LoginServer.default:
        session.mark_server_selected()
        return

    navigator.navigate_to(PageName.SERVER_SELECT)
    navigator.navigate_to(PageName.LOGIN_PAGE, server=wanted.value)
    session.mark_server_selected()


def _restart_game(ctx: ContextHandle) -> None:
    """SL：强杀游戏并清空导航栈，之后由调用方重新走初始化。

    Args:
        ctx: 提供设备服务与任务事实的 dispatch 上下文句柄。
    """
    package = ctx.runtime.config.account.package_name
    _log.warning('[DISPATCH] 启动 → 强制重启游戏：package={!r}', package)
    ctx.runtime.ctrl.stop_app(package)
    time.sleep(_RESTART_SETTLE_SECONDS)
    # 游戏重开后栈里的页面已经不存在；不清空的话下一次 navigate_to 会被
    # 「已在目标页面」短路掉，实际却停在登录页。
    get_session().clear_pages()


def _wait_for_app_process(ctx: ContextHandle, package: str) -> bool:
    """等游戏进程出现；进程一出现就返回，不做固定秒数的空等。

    Args:
        ctx: 提供设备服务与任务事实的 dispatch 上下文句柄。
        package: Android 包名。

    Returns:
        超时前进程出现时为真。
    """
    ctrl = ctx.runtime.ctrl
    deadline = time.monotonic() + _APP_PROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if ctrl.check_app_running(package):
            return True
        time.sleep(_APP_PROCESS_POLL_SECONDS)
    return False


__all__ = ['ensure_ready']
