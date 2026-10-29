"""执行器基类 — 处理器驱动模型下的被动域专家。

架构位置:

    请求 (GUI/CLI/定时器) → 处理器 (dispatch.processor: 分辨/排队/打断决策)
        → 执行器 (本基类的子类: 判断任务怎么执行)
            → 导航器 (NavigationService, 移动外包) + 域内业务操作 → 回主页上报

断点协议:
    导航器在每条边确认到达并压栈之后调 ContextHandle.check_interrupt()。
    处理器置位让路开关 → 执行器在最近一个断点抛 TaskPaused / TaskStopped 让出
    执行权。处理器跑完加急请求后清除信号并重新派发 → 执行器**从头重跑** (幂等,
    游戏状态实时识别所以重跑天然安全), 任务级进度 (self.progress) 保留。

    暂停与插队由处理器决定要不要清导航栈 (见 dispatch.processor); 终止的收尾
    — 清栈、回主页、必要时重新初始化 — 由本基类统一负责, 子类不用管。

子类约定:
    - 实现 _execute(), 用 self._wait() 代替 time.sleep 就能获得业务侧断点;
      连续动作 (选章选节之类) 由导航器在动作内部断, 业务层不用拆。
    - 用 self._report(event, **data) 上报业务事件 (计数/进度)。
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from autowsgr.application.signals import TaskPaused, TaskStopped
from autowsgr.common.system.logger import get_logger
from autowsgr.dispatch.context.state import InterruptSignals


if TYPE_CHECKING:
    from collections.abc import Callable

    from autowsgr.application.runtime import RuntimeContext as GameContext


_log = get_logger('dispatch.executor')


class BaseExecutor:
    """执行器基类: 事件上报 + 断点收尾。"""

    def __init__(
        self,
        ctx: GameContext,
        params: dict | None = None,
        *,
        task_type: str | None = None,
        pause: threading.Event | None = None,
        stop: threading.Event | None = None,
        progress: dict | None = None,
        on_event: Callable[..., None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.params = dict(params or {})
        self.task_type = task_type
        """处理器下发的业务类型。"""
        self.progress = progress if progress is not None else {}
        """任务级进度 (如 fought 计数), 暂停重跑后由处理器传入同一 dict 保留。"""
        self._signals = InterruptSignals(
            pause=pause if pause is not None else threading.Event(),
            stop=stop if stop is not None else threading.Event(),
        )
        self._on_event = on_event

    def run(self) -> Any:
        """任务入口 (单趟): 正常返回结果; 断点收到信号时让出执行权。

        重跑循环归处理器管 (它要先跑加急请求再重新派发本任务)。

        Raises:
            TaskPaused: 断点收到暂停或插队信号。
            TaskStopped: 断点收到终止信号, 回主页收尾已完成。
        """
        try:
            return self._execute()
        except TaskStopped:
            self._navigate_to_home()
            self._report('stopped')
            raise
        except TaskPaused:
            self._report('paused')
            raise

    def _execute(self) -> Any:
        """子类实现: 任务的完整执行过程。"""
        raise NotImplementedError

    def _wait(self, seconds: float) -> None:
        """唯一等待出口 = 业务侧免费断点: 等待前查信号。"""
        self._signals.check()
        time.sleep(seconds)

    def _navigate_to_home(self) -> None:
        """终止收尾: 清掉不可信的导航栈, 不看断点地把游戏带回主页。

        停止开关此时还亮着, 这一趟必须关掉断点检查, 否则导航器会立刻再抛一次。
        栈要先清空, 否则 navigate_to 看到「已经在主页」会直接返回、不确认到达。
        回不去说明游戏已经不在任何已知页面上, 交给处理器重新初始化 (等价重启游戏)。
        """
        from autowsgr.application.ui.navigation.service import NavigationService
        from autowsgr.application.ui.navigation.types import PageName
        from autowsgr.dispatch.context import context
        from autowsgr.dispatch.session import get_session

        get_session().clear_pages()
        try:
            service = NavigationService(context.request(), checkpoint=False)
            service.navigate_to(PageName.HOME)
        except Exception as exc:
            _log.warning('[Executor] 终止后回主页失败, 改为重新初始化: {}', exc)
            from autowsgr.dispatch.startup import ensure_ready

            ensure_ready(self.ctx)

    def _report(self, event: str, **data: Any) -> None:
        """上报业务事件 (panel_ready / rival_done / paused ...), 处理器转发。"""
        if self._on_event is not None:
            self._on_event(event, **data)


__all__ = ['BaseExecutor']
