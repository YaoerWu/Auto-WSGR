"""Contract tests for the dispatch-owned task context."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from autowsgr.application.signals import TaskPaused, TaskStopped
from autowsgr.dispatch.context import (
    ContextClosedError,
    ContextFieldError,
    ContextManager,
    ContextNotBoundError,
    ContextTemplate,
    InterruptSignals,
    RuntimeBindings,
)
from autowsgr.dispatch.context.manager import _ACTIVE_BINDING


def test_context_is_lazy_and_keeps_navigation_facts() -> None:
    manager = ContextManager()
    template = ContextTemplate.for_task('navigation_checker')
    screen = np.zeros((2, 3, 3), dtype=np.uint8)

    with manager.bind('task-1', template=template):
        first = manager.request()
        second = manager.request()

        assert first.task_id == second.task_id == 'task-1'
        assert first.task_type == 'navigation_checker'

        first.record_screenshot(screen)
        first.set_current_page('首页')
        first.set_target_page('首页')
        first.record_route_step(0)

        assert np.array_equal(second.read_latest_screenshot(), screen)
        assert second.read_current_page() == '首页'
        assert second.read_target_page() == '首页'

        result = object()
        first.record_result(result)
        assert second.read_result() is result

        manager.close()
        with pytest.raises(ContextClosedError):
            first.read_current_page()


def test_context_requires_a_bound_scope() -> None:
    with pytest.raises(ContextNotBoundError):
        ContextManager().request()


def test_context_state_does_not_cross_task_scopes() -> None:
    manager = ContextManager()
    template = ContextTemplate.for_task('navigation_checker')

    with manager.bind('task-a', template=template):
        manager.request().set_current_page('首页')

    with manager.bind('task-b', template=template):
        assert manager.request().read_current_page() is None


def test_context_carries_activity_binding() -> None:
    template = ContextTemplate.for_task('event_fight', event_type='stage_push', event_stage='EX7')
    manager = ContextManager()

    with manager.bind('event-task', template=template):
        handle = manager.request()

        assert handle.task_type == 'event_fight'
        assert handle.read_event_type() == 'stage_push'
        assert handle.read_event_stage() == 'EX7'


def test_context_leaves_activity_binding_empty_for_plain_tasks() -> None:
    manager = ContextManager()
    template = ContextTemplate.for_task('navigation_checker')

    with manager.bind('plain-task', template=template):
        handle = manager.request()

        assert handle.read_event_type() is None
        assert handle.read_event_stage() is None


def test_runtime_bindings_are_scope_bound() -> None:
    manager = ContextManager()
    template = ContextTemplate.for_task('navigation_checker')
    runtime = RuntimeBindings(ctrl=object(), config=object(), ocr=None, ship_ocr=None)

    with manager.bind('runtime-task', template=template, runtime=runtime):
        handle = manager.request()
        assert handle.runtime is runtime
        assert handle.runtime.ctrl is runtime.ctrl
        manager.close()
        with pytest.raises(ContextClosedError):
            _ = handle.runtime

    with (
        manager.bind('task-without-runtime', template=template),
        pytest.raises(
            ContextFieldError,
        ),
    ):
        _ = manager.request().runtime


def test_check_interrupt_returns_without_bound_switches() -> None:
    manager = ContextManager()
    with manager.bind('plain-task', template=ContextTemplate.for_task('navigation_checker')):
        manager.request().check_interrupt()


def _check_interrupt_with(
    manager: ContextManager, pause: threading.Event, stop: threading.Event
) -> None:
    signals = InterruptSignals(pause=pause, stop=stop)
    with manager.bind(
        'interrupt-task',
        template=ContextTemplate.for_task('navigation_checker'),
        interrupt=signals,
    ):
        manager.request().check_interrupt()


def test_check_interrupt_stays_quiet_while_switches_are_clear() -> None:
    _check_interrupt_with(ContextManager(), threading.Event(), threading.Event())


def test_check_interrupt_raises_pause_when_pause_switch_is_set() -> None:
    pause = threading.Event()
    pause.set()
    with pytest.raises(TaskPaused):
        _check_interrupt_with(ContextManager(), pause, threading.Event())


def test_check_interrupt_prefers_stop_over_pause() -> None:
    pause, stop = threading.Event(), threading.Event()
    pause.set()
    stop.set()
    with pytest.raises(TaskStopped):
        _check_interrupt_with(ContextManager(), pause, stop)


def test_close_drops_interrupt_switches_with_the_scope() -> None:
    manager = ContextManager()
    runtime = RuntimeBindings(ctrl=object(), config=object(), ocr=None, ship_ocr=None)
    signals = InterruptSignals(pause=threading.Event(), stop=threading.Event())

    with manager.bind(
        'closing-task',
        template=ContextTemplate.for_task('navigation_checker'),
        runtime=runtime,
        interrupt=signals,
    ):
        manager.request()
        manager.close()

        binding = _ACTIVE_BINDING.get()
        assert binding is not None
        assert binding.runtime is None
        assert binding.interrupt is None


def test_blank_task_id_is_rejected() -> None:
    manager = ContextManager()
    with (
        pytest.raises(ContextFieldError),
        manager.bind('   ', template=ContextTemplate.for_task('navigation_checker')),
    ):
        pass
