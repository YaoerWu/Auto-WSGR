"""模块功能：验证出征准备页的页面族识别与舰队标签识别。

直接调用方：项目测试运行器。
直接依赖：sortie.battle_preparation.checker 与 navigation.types。
边界：不读模板文件、不截图；识别入口用替身接管。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sortie.battle_preparation import checker as checker_module
from autowsgr.application.navigation.types import PageName


if TYPE_CHECKING:
    import pytest


def _match(matched: bool, score: float = 0.9) -> SimpleNamespace:
    """构造一条模板命中事实。"""
    return SimpleNamespace(matched=matched, score=score)


def _patch_expect_template(
    monkeypatch: pytest.MonkeyPatch,
    observations: list[SimpleNamespace],
) -> dict[str, Any]:
    """把模板识别换成固定结论，并记录收到的识别参数。"""
    captured: dict[str, Any] = {}

    def _fake(_ctx: Any, **options: Any) -> SimpleNamespace:
        captured.clear()
        captured.update(options)
        return SimpleNamespace(
            satisfied=any(match.matched for match in observations), observation=observations
        )

    monkeypatch.setattr(checker_module, 'expect_template', _fake)
    monkeypatch.setattr(
        checker_module,
        'load_ui_template',
        lambda namespace, filename: (namespace, filename),
    )
    return captured


def test_read_layer_reports_matched_preparation_pages(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四种准备页一次比对完，按页面顺序返回命中的页面，全不中返回空。"""
    captured = _patch_expect_template(
        monkeypatch,
        [_match(False), _match(True), _match(False), _match(False)],
    )

    assert checker_module.read_battle_preparation_layer(ctx) == (
        PageName.DECISIVE_BATTLE_PREPARATION,
    )
    assert captured['template'] == tuple(
        (checker_module.constants.TEMPLATE_NAMESPACE, filename)
        for _page, filename in checker_module.constants.PREPARATION_TEMPLATES
    )
    assert captured['roi'] is checker_module.constants.BATTLE_PREPARATION_ROI
    assert captured['attempts'] == 5
    assert captured['interval_seconds'] == 0.5

    _patch_expect_template(
        monkeypatch,
        [_match(True), _match(False), _match(False), _match(True)],
    )

    assert checker_module.read_battle_preparation_layer(ctx) == (
        PageName.EXERCISE_PREPARATION,
        PageName.BATTLE_PREPARATION,
    )

    _patch_expect_template(monkeypatch, [_match(False) for _ in range(4)])

    assert checker_module.read_battle_preparation_layer(ctx) == ()


def test_read_team_tab_returns_active_team(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四队模板与各自区域按序比对，只亮一队时返回其编号。"""
    for team in (1, 2, 3, 4):
        _patch_expect_template(
            monkeypatch,
            [_match(index == team - 1) for index in range(4)],
        )
        captured = _patch_expect_template(
            monkeypatch,
            [_match(index == team - 1) for index in range(4)],
        )

        assert checker_module.read_team_tab(ctx) == team
        assert captured['template'] == tuple(
            (checker_module.constants.TEMPLATE_NAMESPACE, filename)
            for filename in checker_module.constants.TEAM_TAB_TEMPLATES
        )
        assert captured['roi'] is checker_module.constants.TEAM_TAB_ROIS


def test_read_team_tab_reads_observation_and_prefers_higher_score(
    ctx: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """识别入口报不满足时仍按逐队事实取编号；相邻两队同时命中取分高者；全不中返回空。"""
    _patch_expect_template(
        monkeypatch,
        [_match(False), _match(True, score=0.99), _match(False), _match(False)],
    )
    assert checker_module.read_team_tab(ctx) == 2

    _patch_expect_template(
        monkeypatch,
        [_match(True, score=0.88), _match(True, score=0.93), _match(False), _match(False)],
    )
    assert checker_module.read_team_tab(ctx) == 2

    captured = _patch_expect_template(monkeypatch, [_match(False) for _ in range(4)])
    assert checker_module.read_team_tab(ctx, attempts=2, interval_seconds=0.1) is None
    assert captured['attempts'] == 2
    assert captured['interval_seconds'] == 0.1
