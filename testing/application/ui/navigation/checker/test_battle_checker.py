"""模块功能：验证出征页章节识别与页内导航的判定契约。

直接调用方：项目测试运行器。

直接依赖：pytest、checker.sortie.battle 与 vision 识别结果类型。

边界：用替身接管识别入口，不加载 OCR 模型、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller.sortie.battle import checker as battle_checker
from autowsgr.common.vision import TextDetection


def _detection(text: str, confidence: float = 0.9) -> TextDetection:
    """构造一条 OCR 识别结果。"""
    return TextDetection(recognized_text=text, confidence_score=confidence)


def _install_ocr(monkeypatch: pytest.MonkeyPatch, groups: list[list[TextDetection]]) -> list:
    """用替身接管 OCR 入口，并记录调用参数。"""
    calls: list[dict[str, object]] = []

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        calls.append(options)
        return SimpleNamespace(satisfied=True, observation=groups)

    monkeypatch.setattr(battle_checker, 'expect_ocr', expect_ocr)
    return calls


# ── 章节标签解析 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('第3章', 3),
        ('三章', 3),
        ('第 十 章', 10),
        ('第十一章', None),
        ('---', None),
        ('', None),
    ],
)
def test_parse_chapter_label(text: str, expected: int | None) -> None:
    """只有 1-10 章的合法标签能解析出章号。"""
    assert battle_checker._parse_chapter_label(text) is expected


# ── 地图标题解析 ─────────────────────────────────────────────────────────────


def test_parse_map_title_uses_database_name() -> None:
    """标题里的章-节与地图名解析成结构化标识。"""
    identity = battle_checker._parse_map_title('1-3 仁州附近海域')

    assert identity is not None
    assert (identity.chapter, identity.map_num, identity.name) == (1, 3, '仁州附近海域')


def test_parse_map_title_fixes_stuck_digits() -> None:
    """OCR 把节号粘连成两位数时按首位数校正。"""
    identity = battle_checker._parse_map_title('1-13 仁州')

    assert identity is not None
    assert (identity.chapter, identity.map_num) == (1, 1)


def test_parse_map_title_rejects_unknown_text() -> None:
    """没有章号节号的标题解析失败。"""
    assert battle_checker._parse_map_title('仁州附近海域') is None


# ── 一帧读章节状态 ───────────────────────────────────────────────────────────


def test_read_chapter_state_reads_all_regions_in_one_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五个槽位与标题共用一次截图，当前章取中间槽位。"""
    groups = [
        [_detection('第一章')],
        [_detection('第二章')],
        [_detection('第三章')],
        [_detection('第四章')],
        [_detection('第五章')],
        [_detection('3-2 东南群岛（1）')],
    ]
    calls = _install_ocr(monkeypatch, groups)

    slots, current = battle_checker._read_chapter_state(object())

    assert current == 3
    assert [slot.chapter for slot in slots] == [1, 2, 3, 4, 5]
    assert len(calls) == 1
    assert len(calls[0]['roi']) == len(battle_checker.CHAPTER_SLOT_ROIS) + 1


def test_read_chapter_state_falls_back_to_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """中间槽位读不出章号时退回地图标题。"""
    groups = [
        [_detection('')],
        [_detection('')],
        [_detection('')],
        [_detection('')],
        [_detection('')],
        [_detection('2-4 深海扶桑基地')],
    ]
    _install_ocr(monkeypatch, groups)

    _slots, current = battle_checker._read_chapter_state(object())

    assert current == 2


# ── 选章落点 ─────────────────────────────────────────────────────────────────


def _slots(*chapters: int | None) -> tuple:
    """按给定章号构造章节槽位。"""
    return tuple(
        battle_checker.ChapterSlot(
            index=index,
            chapter=chapter,
            text=f'{chapter}' if chapter is not None else '',
            confidence=0.9,
        )
        for index, chapter in enumerate(chapters)
    )


def test_calculate_chapter_slot_uses_visible_target() -> None:
    """视图内已经可见目标章时直接点它。"""
    slots = _slots(1, 2, 3, 4, 5)

    assert battle_checker._calculate_chapter_slot(3, 5, slots) == 4


def test_calculate_chapter_slot_steps_toward_target() -> None:
    """目标不可见时按步长向目标方向移动一格。"""
    slots = _slots(1, 2, 3, 4, 5)

    assert battle_checker._calculate_chapter_slot(3, 4, slots) == 3
    assert battle_checker._calculate_chapter_slot(3, 1, slots) == 0


def test_calculate_chapter_slot_needs_verified_target() -> None:
    """算出的槽位识别值对不上预期章号时不点。"""
    slots = _slots(1, 2, 3, 9, 5)

    assert battle_checker._calculate_chapter_slot(3, 4, slots) is None


# ── 地图采样稳定性 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('samples', 'expected'),
    [
        ([], (None, False)),
        ([7, 7], (7, True)),
        ([7, 8, 8], (8, True)),
    ],
)
def test_judge_stable_map_number(samples: list[int], expected: tuple[int | None, bool]) -> None:
    """末两次相同或采满全相同才判稳定。"""
    assert battle_checker._judge_stable_map_number(samples) == expected


def test_judge_stable_map_number_flags_jitter() -> None:
    """采样结果来回跳时标记为不稳定，避免按抖动值点击。"""
    assert battle_checker._judge_stable_map_number([7, 8, 7]) == (7, False)
