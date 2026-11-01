"""模块功能：验证演习对手识别的事实解析契约。

直接调用方：项目测试运行器。

直接依赖：pytest、ships.models.exercise 与 common.vision 的文本识别结果。

边界：用替身接管 OCR 入口，不截图、不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.application.ui.ships.models import exercise
from autowsgr.application.ui.ships.types import ShipType
from autowsgr.common.vision import TextDetection


if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest


def _install(
    monkeypatch: pytest.MonkeyPatch,
    ship_types: Sequence[str | None],
    levels: Sequence[str | None],
) -> None:
    """按识别区域返回预设的 OCR 文本，空字符串表示没有识别结果。"""

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        texts = ship_types if options.get('roi') is exercise._SHIP_TYPE_ROIS else levels
        observation = [[] if text is None else [TextDetection(text, 0.9)] for text in texts]
        return SimpleNamespace(observation=observation)

    monkeypatch.setattr(exercise, 'expect_ocr', expect_ocr)


def test_recognize_rivals_reads_six_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    """六个槽位各读到舰种与等级时按槽位号升序返回。"""
    _install(
        monkeypatch,
        ['航母', '轻母', '战列', '驱逐', '潜艇', '雷巡'],
        ['LV.110', 'LV.98', 'LV.105', 'LV.87', 'LV.92', 'LV.101'],
    )

    ships = exercise.recognize_rivals(object())

    assert [ship.slot for ship in ships] == [1, 2, 3, 4, 5, 6]
    assert [ship.ship_type.value for ship in ships] == [
        '航母',
        '轻母',
        '战列',
        '驱逐',
        '潜艇',
        '雷巡',
    ]
    assert [ship.level for ship in ships] == [110, 98, 105, 87, 92, 101]
    assert all(ship.name is None for ship in ships)


def test_recognize_rivals_drops_unknown_ship_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR 把舰种读成错字时不猜，字段留空。"""
    _install(
        monkeypatch,
        ['轻由', '轻母', None, None, None, None],
        [None, 'LV.98', None, None, None, None],
    )

    ships = exercise.recognize_rivals(object())

    assert ships[0].ship_type is None
    assert ships[0].level is None
    assert ships[1].ship_type.value == '轻母'
    assert ships[1].level == 98
    assert ships[2].ship_type is None


def test_recognize_rivals_accepts_text_split_across_detections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一区域被切成多段识别结果时拼接后再解析。"""

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        if options.get('roi') is exercise._SHIP_TYPE_ROIS:
            detections = [
                [TextDetection('轻', 0.9), TextDetection('母', 0.9)],
                [],
                [],
                [],
                [],
                [],
            ]
            return SimpleNamespace(observation=detections)
        return SimpleNamespace(observation=[[] for _ in range(exercise.EXERCISE_RIVAL_SLOTS)])

    monkeypatch.setattr(exercise, 'expect_ocr', expect_ocr)

    ships = exercise.recognize_rivals(object())

    assert ships[0].ship_type is ShipType.CVL


def test_recognize_rivals_reads_level_with_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    """等级文本带前导字母或标点时只取数字部分。"""
    _install(
        monkeypatch,
        [None, None, None, None, None, None],
        ['LV.110', 'LV.98', 'Lv105', '110', 'LV.', None],
    )

    levels = [ship.level for ship in exercise.recognize_rivals(object())]

    assert levels == [110, 98, 105, 110, None, None]
