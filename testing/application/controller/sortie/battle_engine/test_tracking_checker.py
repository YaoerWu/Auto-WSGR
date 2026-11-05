"""模块功能：验证地图船只观测的黄色簇定位与索敌页排除。

直接调用方：项目测试运行器。

直接依赖：pytest、numpy、battle_engine.tracking 的观测入口。

边界：只驱动单帧观测，不截图、不点击、不访问设备。
"""

from __future__ import annotations

import numpy
import pytest

from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase
from autowsgr.application.controller.sortie.battle_engine.tracking import (
    checker as tracking_checker,
)


def _frame_with_ship(
    left: int = 400,
    top: int = 300,
    size: int = 20,
) -> numpy.ndarray:
    """构造一张只有一个小黄块的帧。"""
    frame = numpy.zeros((720, 1280, 3), dtype=numpy.uint8)
    frame[top : top + size, left : left + size] = (239, 219, 106)
    return frame


def test_read_yellow_cluster_returns_normalized_centroid() -> None:
    """黄色簇的质心按归一化坐标返回。"""
    center = tracking_checker.read_yellow_cluster(_frame_with_ship())

    assert center is not None
    # 连通域质心取像素索引中心：20px 方块覆盖 400..419，质心落在 409.5。
    assert center[0] == pytest.approx(409.5 / 1280)
    assert center[1] == pytest.approx(309.5 / 720)


def test_read_yellow_cluster_ignores_small_blobs() -> None:
    """面积不足的黄色噪点被丢弃。"""
    assert tracking_checker.read_yellow_cluster(_frame_with_ship(size=5)) is None


def test_read_ship_position_skips_spot_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """索敌页上不追船，直接返回空。"""
    monkeypatch.setattr(
        tracking_checker,
        'read_phase_from_frame',
        lambda _frame, _candidates: CombatPhase.SPOT_ENEMY_SUCCESS,
    )

    assert tracking_checker.read_ship_position_from_frame(_frame_with_ship()) is None


def test_check_spot_page_reports_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """阶段判定命中索敌页时返回真。"""
    monkeypatch.setattr(
        tracking_checker,
        'read_phase_from_frame',
        lambda _frame, _candidates: CombatPhase.SPOT_ENEMY_SUCCESS,
    )

    assert tracking_checker.check_spot_page(_frame_with_ship()) is True
