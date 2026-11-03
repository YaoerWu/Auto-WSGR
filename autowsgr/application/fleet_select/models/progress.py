"""模块功能：把换船进度上报给业务层。

上层调用：
- fleet_select.models：三套换船编排在动作完成时上报。

下层依赖：
- 无。

边界：只转交回调，不判断事件含义，不保存状态。
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable


def report_progress(
    notify: Callable[[str, dict[str, object]], None] | None,
    event_name: str,
    facts: dict[str, object],
) -> None:
    """把一次换船进度转交给业务层回调，没有回调时什么也不做。

    Args:
        notify: 业务层传入的进度回调，可为空。
        event_name: 事件名，例如 fleet_validation 或 fleet_checkpoint。
        facts: 事件携带的事实。
    """
    if notify is not None:
        notify(event_name, facts)


__all__ = ['report_progress']
