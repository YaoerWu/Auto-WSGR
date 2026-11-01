"""模块功能：验证船只识别入口的任务类型路由契约。

直接调用方：项目测试运行器。

直接依赖：pytest 与 ships.service。

边界：用替身接管识别域，不截图、不访问设备。
"""

from __future__ import annotations

import pytest

from autowsgr.application.ui.ships import service
from autowsgr.application.ui.ships.models import ShipInfo
from autowsgr.application.ui.ships.service import ShipsService
from autowsgr.application.ui.ships.types import ShipTaskType


def test_recognize_ships_info_routes_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    """演习任务类型走演习对手识别域。"""
    calls: list[object] = []
    sentinel = (ShipInfo(slot=1),)

    def recognize_rivals(ctx: object) -> tuple[ShipInfo, ...]:
        calls.append(ctx)
        return sentinel

    monkeypatch.setattr(service, 'recognize_rivals', recognize_rivals)
    ctx = object()

    assert ShipsService(ctx).recognize_ships_info(ShipTaskType.EXERCISE) is sentinel
    assert calls == [ctx]


def test_recognize_ships_info_rejects_unknown_task_type() -> None:
    """没有识别域的任务类型直接报错，不静默返回空结果。"""
    with pytest.raises(ValueError, match='任务类型没有船只识别域'):
        ShipsService(object()).recognize_ships_info('normal_fight')
