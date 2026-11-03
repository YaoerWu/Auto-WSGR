"""模块功能：验证换船前的舰队标签切换。

直接调用方：项目测试运行器。

直接依赖：fleet_select.operation.team_select。

边界：读队标签与点队标签换成替身，不读截图、不点设备。
"""

from __future__ import annotations

from typing import Any

import pytest

from autowsgr.application.errors import ActionFailedError
from autowsgr.application.fleet_select.operation import team_select as team_select_module
from autowsgr.application.fleet_select.operation.team_select import select_team


def _patch_tab(
    monkeypatch: pytest.MonkeyPatch,
    current: int | None,
    *,
    switched: int | None = None,
) -> list[int]:
    """固定读到的队标签，并记录点过的队标签。

    Args:
        monkeypatch: pytest 的替换夹具。
        current: 点击之前读到的队标签。
        switched: 点击之后复核读到的队标签；不传时与 current 相同。

    Returns:
        依次记录下来的点击目标。
    """
    clicks: list[int] = []
    reads: list[int | None] = [current, current if switched is None else switched]

    def read_team_tab(_ctx: Any) -> int | None:
        return reads.pop(0) if len(reads) > 1 else reads[0]

    monkeypatch.setattr(team_select_module, 'read_team_tab', read_team_tab)
    monkeypatch.setattr(
        team_select_module,
        'BattlePreparationPage',
        lambda _ctx: type(
            'FakePage',
            (),
            {'click_team_tab': lambda _self, team: clicks.append(team)},
        )(),
    )
    return clicks


def test_switch_skips_when_fleet_already_selected(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前已经是目标队时不重复点击。"""
    clicks = _patch_tab(monkeypatch, 2)

    select_team(ctx, 2)

    assert clicks == []


def test_switch_clicks_target_fleet(ctx: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """当前队与目标队不同时点一次目标标签。"""
    clicks = _patch_tab(monkeypatch, 1, switched=3)

    select_team(ctx, 3)

    assert clicks == [3]


def test_switch_ignores_missing_fleet_id(ctx: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有目标队时不读页面、不点击。"""
    clicks = _patch_tab(monkeypatch, 1)

    select_team(ctx, None)

    assert clicks == []


def test_switch_reports_when_fleet_does_not_switch(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """点完标签后复核仍是旧队时按失败处理。"""
    _patch_tab(monkeypatch, 1, switched=1)

    with pytest.raises(ActionFailedError, match='点了第 3 队之后读到的是第 1 队'):
        select_team(ctx, 3)


@pytest.mark.parametrize('fleet_id', [0, 5])
def test_switch_rejects_out_of_range_fleet(ctx: Any, fleet_id: int) -> None:
    """舰队编号越界时在读页面之前报错。"""
    with pytest.raises(ValueError, match='舰队编号必须在 1 到 4 之间'):
        select_team(ctx, fleet_id)
