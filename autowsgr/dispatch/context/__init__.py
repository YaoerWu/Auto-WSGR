"""Dispatch-owned task context public entry."""

from __future__ import annotations

from .errors import ContextClosedError, ContextError, ContextFieldError, ContextNotBoundError
from .manager import ContextHandle, ContextManager
from .runtime import RuntimeBindings
from .state import InterruptSignals
from .template import ContextTemplate


context = ContextManager()


__all__ = [
    'ContextClosedError',
    'ContextError',
    'ContextFieldError',
    'ContextHandle',
    'ContextManager',
    'ContextNotBoundError',
    'ContextTemplate',
    'InterruptSignals',
    'RuntimeBindings',
    'context',
]
