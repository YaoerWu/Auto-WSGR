"""Lifecycle and semantic access for the dispatch task context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .errors import ContextClosedError, ContextFieldError, ContextNotBoundError, ContextScopeError
from .state import InterruptSignals, TaskContextState
from .template import _require_text


if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np

    from .runtime import RuntimeBindings
    from .template import ContextTemplate


@dataclass(frozen=True, slots=True)
class _Binding:
    manager: ContextManager
    task_id: str
    template: ContextTemplate
    runtime: RuntimeBindings | None
    interrupt: InterruptSignals | None


_ACTIVE_BINDING: ContextVar[_Binding | None] = ContextVar('_ACTIVE_BINDING', default=None)


class ContextHandle:
    """Semantic access handle for one active task context."""

    def __init__(self, manager: ContextManager, task_id: str) -> None:
        self._manager = manager
        self._task_id = task_id

    @property
    def task_id(self) -> str:
        """Return the bound task identifier."""
        return self._task_id

    @property
    def task_type(self) -> str:
        """Return the task type from the initialization template."""
        return self._state().template.task_type

    @property
    def runtime(self) -> RuntimeBindings:
        """Return runtime service references bound to the active task scope."""
        self._state()
        return self._manager._require_runtime(self._task_id)

    def record_screenshot(self, screen: np.ndarray) -> None:
        """Store a private copy of the latest RGB screenshot."""
        if not hasattr(screen, 'copy'):
            raise ContextFieldError('截图必须提供 copy() 方法')
        self._state().latest_screenshot = screen.copy()

    def read_latest_screenshot(self) -> np.ndarray:
        """Return a copy of the latest screenshot."""
        screen = self._state().latest_screenshot
        if screen is None:
            raise ContextFieldError('当前任务尚未记录截图')
        return screen.copy()

    def set_current_page(self, page: str) -> None:
        """Record a page fact confirmed by the navigator."""
        self._state().current_page = _require_text(page, 'current_page')

    def read_current_page(self) -> str | None:
        """Return the last confirmed page fact, if any."""
        return self._state().current_page

    def set_target_page(self, page: str) -> None:
        """Record the requested destination page."""
        self._state().target_page = _require_text(page, 'target_page')

    def read_target_page(self) -> str | None:
        """Return the requested destination page, if any."""
        return self._state().target_page

    def read_event_type(self) -> str | None:
        """Return the activity type bound to the active task, if any."""
        return self._state().template.event_type

    def read_event_stage(self) -> str | None:
        """Return the activity stage bound to the active task, if any."""
        return self._state().template.event_stage

    def record_route_step(self, step: int) -> None:
        """Record the current zero-based route step."""
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise ContextFieldError('route_step 必须是非负整数')
        self._state().route_step = step

    def record_result(self, result: Any) -> None:
        """Record the latest transition or recognition result."""
        self._state().last_result = result

    def read_result(self) -> Any:
        """Return the latest transition or recognition result."""
        return self._state().last_result

    def record_error(self, error: BaseException | str) -> None:
        """Record an error fact without retaining a traceback or exception object."""
        self._state().last_error = str(error)

    def check_interrupt(self) -> None:
        """让出执行权的唯一检查点：dispatch 要求暂停或终止时抛出对应信号。

        执行器只在边与边之间调用它，所以抛出位置天然是「刚确认到达、导航栈已记账」的
        安全点，回退路径完整。未绑定让路开关时直接返回，便于单测构造裸上下文。

        Raises:
            TaskStopped: 处理器已请求终止，执行器应回主页再结束任务。
            TaskPaused: 处理器请求暂停，或有更高优先级任务插队。
        """
        signals = self._state().interrupt
        if signals is None:
            return
        signals.check()

    def _state(self) -> TaskContextState:
        return self._manager._require_state(self._task_id)


class ContextManager:
    """Own task contexts and expose lazy, scope-bound access."""

    def __init__(self) -> None:
        self._states: dict[str, TaskContextState] = {}

    @contextmanager
    def bind(
        self,
        task_id: str,
        *,
        template: ContextTemplate,
        runtime: RuntimeBindings | None = None,
        interrupt: InterruptSignals | None = None,
    ) -> Iterator[None]:
        """Bind task facts, runtime service references and interrupt switches without creating state."""
        task_id = _require_text(task_id, 'task_id')
        active = _ACTIVE_BINDING.get()
        if active is not None:
            raise ContextScopeError(f'已有活动任务作用域: {active.task_id}')

        token = _ACTIVE_BINDING.set(_Binding(self, task_id, template, runtime, interrupt))
        try:
            yield
        finally:
            state = self._states.pop(task_id, None)
            if state is not None:
                state.closed = True
            _ACTIVE_BINDING.reset(token)

    def request(self) -> ContextHandle:
        """Return the active context, creating it on the first request."""
        binding = _ACTIVE_BINDING.get()
        if binding is None or binding.manager is not self:
            raise ContextNotBoundError('当前执行流没有绑定 dispatch Context')

        state = self._states.get(binding.task_id)
        if state is None:
            state = TaskContextState(
                task_id=binding.task_id,
                template=binding.template,
                interrupt=binding.interrupt,
            )
            self._states[binding.task_id] = state
        if state.closed:
            raise ContextClosedError(f'任务上下文已关闭: {binding.task_id}')
        return ContextHandle(self, binding.task_id)

    def close(self) -> None:
        """Close the active task context before its binding scope exits."""
        binding = _ACTIVE_BINDING.get()
        if binding is None or binding.manager is not self:
            raise ContextNotBoundError('当前执行流没有绑定 dispatch Context')
        state = self._states.get(binding.task_id)
        if state is None:
            raise ContextClosedError(f'任务上下文尚未创建: {binding.task_id}')
        state.closed = True
        _ACTIVE_BINDING.set(_Binding(self, binding.task_id, binding.template, None, None))

    def _require_runtime(self, task_id: str) -> RuntimeBindings:
        binding = _ACTIVE_BINDING.get()
        if binding is None or binding.manager is not self or binding.task_id != task_id:
            raise ContextNotBoundError('当前执行流没有绑定 runtime service references')
        if binding.runtime is None:
            raise ContextFieldError('当前任务作用域未绑定 runtime service references')
        return binding.runtime

    def _require_state(self, task_id: str) -> TaskContextState:
        state = self._states.get(task_id)
        if state is None or state.closed:
            raise ContextClosedError(f'任务上下文不可用: {task_id}')
        return state


__all__ = ['ContextHandle', 'ContextManager']
