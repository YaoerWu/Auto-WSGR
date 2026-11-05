"""模块功能：验证战斗阶段判定的命中、否决与优先级。

直接调用方：项目测试运行器。

直接依赖：pytest、numpy、battle_engine.monitor 的阶段判据与判定入口。

边界：只驱动单帧判定，不截图、不点击、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy

from autowsgr.application.controller.sortie.battle_engine.monitor import checker as monitor_checker
from autowsgr.application.controller.sortie.battle_engine.monitor.constants import PHASE_SIGNATURES
from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase


if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest


def _frame() -> numpy.ndarray:
    """构造一张全黑的标准分辨率帧。"""
    return numpy.zeros((720, 1280, 3), dtype=numpy.uint8)


def _install_scores(
    monkeypatch: pytest.MonkeyPatch,
    scores: dict[str, float],
) -> None:
    """让模板匹配按模板键返回预设分数，并跳过模板读盘。"""

    def match_templates(
        _frame: numpy.ndarray,
        templates: Sequence[Any],
        *,
        confidence: float = 0.8,
    ) -> list[SimpleNamespace]:
        del confidence
        return [
            SimpleNamespace(score=scores.get(key, 0.0), matched=False, center=None)
            for key in templates
        ]

    monkeypatch.setattr(monitor_checker, '_load_template', lambda key: key)
    monkeypatch.setattr(monitor_checker.adapters, 'match_templates', match_templates)


def _install_pixels(monkeypatch: pytest.MonkeyPatch, *, matched: bool) -> None:
    """让像素签名匹配返回固定结论。"""

    def match_pixels(
        _frame: numpy.ndarray,
        _signature: object,
    ) -> list[SimpleNamespace]:
        return [SimpleNamespace(matched=matched, score=1.0 if matched else 0.0, center=None)]

    monkeypatch.setattr(monitor_checker.adapters, 'match_pixels', match_pixels)


def test_read_phase_from_frame_matches_template_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    """模板分过阈值时返回对应阶段。"""
    _install_scores(monkeypatch, {'fight_condition': 0.9})

    phase = monitor_checker.read_phase_from_frame(_frame(), [CombatPhase.FIGHT_CONDITION])

    assert phase is CombatPhase.FIGHT_CONDITION


def test_read_phase_from_frame_returns_none_below_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模板分没过阈值时视为没命中。"""
    _install_scores(monkeypatch, {'fight_condition': 0.5})

    assert monitor_checker.read_phase_from_frame(_frame(), [CombatPhase.FIGHT_CONDITION]) is None


def test_read_phase_from_frame_respects_exclude_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """否决键命中时跳过该阶段，即使主键已经过阈值。"""
    grade_key = PHASE_SIGNATURES[CombatPhase.RESULT].template_keys[0]
    _install_scores(monkeypatch, {'result_page': 0.9, grade_key: 0.9})

    assert monitor_checker.read_phase_from_frame(_frame(), [CombatPhase.EXP_SETTLEMENT]) is None


def test_read_phase_from_frame_prefers_candidate_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """多个候选同时命中时按候选顺序取第一个。"""
    grade_key = PHASE_SIGNATURES[CombatPhase.RESULT].template_keys[0]
    _install_scores(monkeypatch, {'result_page': 0.9, grade_key: 0.9})

    phase = monitor_checker.read_phase_from_frame(
        _frame(),
        [CombatPhase.RESULT, CombatPhase.EXP_SETTLEMENT],
    )

    assert phase is CombatPhase.RESULT


def test_read_phase_from_frame_uses_pixel_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """只带像素签名的阶段按像素结论判定。"""
    _install_scores(monkeypatch, {})
    _install_pixels(monkeypatch, matched=True)

    assert (
        monitor_checker.read_phase_from_frame(_frame(), [CombatPhase.FORMATION])
        is CombatPhase.FORMATION
    )


def test_read_phase_from_frame_skips_unidentifiable_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有视觉判据的阶段永远不命中。"""
    _install_scores(monkeypatch, {})

    assert monitor_checker.read_phase_from_frame(_frame(), [CombatPhase.START_FIGHT]) is None
