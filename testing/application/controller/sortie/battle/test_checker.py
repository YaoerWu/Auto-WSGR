"""模块功能：验证征战页章节与地图识别的解析、落点计算与稳定性判定。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.sortie.battle.checker 与 vision 识别入口。

边界：只驱动纯函数与单帧识别入口，不点击、不导航、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.application.controller.sortie.battle.checker import (
    ChapterSlot,
    MapIdentity,
    _calculate_chapter_slot,
    _judge_stable_map_number,
    _parse_chapter_label,
    _parse_map_title,
    _read_chapter_state,
)
from autowsgr.common.vision import TextDetection


if TYPE_CHECKING:
    from collections.abc import Sequence


def _detection(text: str, confidence: float = 0.9) -> TextDetection:
    """构造一条 OCR 识别结果。"""
    return TextDetection(recognized_text=text, confidence_score=confidence)


def _slot(index: int, chapter: int | None) -> ChapterSlot:
    """构造一个章节槽位识别事实。"""
    return ChapterSlot(index=index, chapter=chapter, text=f'第{chapter}章', confidence=0.9)


def _install_ocr(monkeypatch: pytest.MonkeyPatch, groups: list[list[TextDetection]]) -> None:
    """让单帧 OCR 返回按识别区域分组的替身结果。"""
    from autowsgr.application.controller.sortie.battle import checker as battle_checker

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        return SimpleNamespace(satisfied=True, observation=groups, options=options)

    monkeypatch.setattr(battle_checker, 'expect_ocr', expect_ocr)


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('第3章', 3),
        ('3章', 3),
        ('三章', 3),
        ('第 十 章', 10),
        ('第十一章', None),
        ('12章', None),
        ('---', None),
        ('', None),
        ('abc', None),
    ],
)
def test_parse_chapter_label(text: str, expected: int | None) -> None:
    """侧栏章节标签按中文与阿拉伯数字解析，越界与噪声返回 None。"""
    assert _parse_chapter_label(text) == expected


def test_parse_map_title_uses_database_name_and_cleans_noise() -> None:
    """标题命中数据表时用库内名称覆盖 OCR 文本，粘连编号按首位数字校正。"""
    assert _parse_map_title('1-3 仁州附近海域') == MapIdentity(
        chapter=1,
        map_num=3,
        name='仁州附近海域',
        raw_text='1-3 仁州附近海域',
    )
    assert _parse_map_title('1-13 仁州') == MapIdentity(
        chapter=1,
        map_num=1,
        name='母港附近海域',
        raw_text='1-13 仁州',
    )
    assert _parse_map_title('2-9 7测试海域') == MapIdentity(
        chapter=2,
        map_num=9,
        name='测试海域',
        raw_text='2-9 7测试海域',
    )
    assert _parse_map_title('仁州附近海域') is None


def test_read_chapter_state_reads_slots_then_falls_back_to_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一帧同时读出五个槽位与标题，当前章节取中间槽位，读不出时用标题章号兜底。"""
    from autowsgr.application.controller.sortie.battle import checker as battle_checker

    _install_ocr(
        monkeypatch,
        [
            [_detection('第1章')],
            [_detection('第2章')],
            [_detection('第3章')],
            [_detection('第4章')],
            [_detection('第5章')],
            [_detection('3-2 东南群岛（1）')],
        ],
    )

    slots, current = _read_chapter_state(object())

    assert [slot.chapter for slot in slots] == [1, 2, 3, 4, 5]
    assert [slot.index for slot in slots] == [0, 1, 2, 3, 4]
    assert current == 3
    assert len(battle_checker.CHAPTER_SLOT_ROIS) == 5

    _install_ocr(
        monkeypatch,
        [
            [_detection('第1章')],
            [_detection('第2章')],
            [_detection('---')],
            [_detection('第4章')],
            [_detection('第5章')],
            [_detection('2-4 深海扶桑基地')],
        ],
    )

    slots, current = _read_chapter_state(object())

    assert slots[2].chapter is None
    assert current == 2


@pytest.mark.parametrize(
    ('current', 'target', 'chapters', 'expected'),
    [
        (3, 5, [1, 2, 3, 4, 5], 4),
        (3, 4, [1, 2, 3, 4, 5], 3),
        (3, 1, [1, 2, 3, 4, 5], 0),
        (3, 3, [1, 2, 3, 4, 5], 2),
        (3, 3, [1, 2, 4, 5, 6], None),
        (3, 5, [1, 2, 3], None),
        (3, 5, [1, 2, 3, 4, None], None),
        (3, 2, [2, 3, 4, 5, 6], 0),
    ],
)
def test_calculate_chapter_slot(
    current: int,
    target: int,
    chapters: Sequence[int | None],
    expected: int | None,
) -> None:
    """槽位落点优先命中目标章，否则按单步或双步移动并回验槽位识别值。"""
    slots = [_slot(index, chapter) for index, chapter in enumerate(chapters)]

    assert _calculate_chapter_slot(current, target, slots) == expected


@pytest.mark.parametrize(
    ('map_numbers', 'expected'),
    [
        ([], (None, False)),
        ([7], (7, False)),
        ([7, 7], (7, True)),
        ([7, 8, 8], (8, True)),
        ([7, 8, 7], (7, False)),
    ],
)
def test_judge_stable_map_number(
    map_numbers: Sequence[int],
    expected: tuple[int | None, bool],
) -> None:
    """末两次相同才算稳定，否则取众数并标记抖动。"""
    assert _judge_stable_map_number(map_numbers) == expected
