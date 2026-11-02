"""测试 地图页面 UI 控制器。"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from autowsgr.application.controller.sortie.battle import BattlePage
from autowsgr.application.runtime.context import GameContext
from autowsgr.application.ui.controller.operations.sortie_page import (
    battle_page,
    decisive_page,
    expedition_page,
    main_page,
)
from autowsgr.application.ui.controller.operations.sortie_page.battle_page import (
    constants,
    recognition,
)
from autowsgr.common.device import AndroidController
from autowsgr.common.vision import OCRResult


ChapterSlot = recognition.ChapterSlot
parse_chapter_label = recognition._parse_chapter_label
parse_map_title = recognition._parse_map_title
_calculate_chapter_slot = battle_page.page._calculate_chapter_slot


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


class TestParseMapTitle:
    def test_standard_format(self):
        info = parse_map_title('9-5南大洋群岛')
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == '南大洋群岛'

    def test_with_slash(self):
        info = parse_map_title('9-5/南大洋群岛')
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == '南大洋群岛'

    def test_with_spaces(self):
        info = parse_map_title('3 - 4 星洲海峡')
        assert info is not None
        assert info.chapter == 3
        assert info.map_num == 4
        # DB name takes precedence
        assert info.name == '星洲海峡'

    def test_numbers_only(self):
        info = parse_map_title('1-1')
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 1
        # 数据库中有 (1,1) → "母港附近海域"
        assert info.name == '母港附近海域'

    def test_numbers_only_unknown(self):
        """未在数据库中的编号保持空名称。"""
        info = parse_map_title('1-9')
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 9
        assert info.name == ''

    def test_with_full_width_slash(self):
        info = parse_map_title('5-3／马耳他附近海域')  # noqa: RUF001
        assert info is not None
        assert info.chapter == 5
        assert info.map_num == 3
        assert info.name == '马耳他附近海域'

    def test_em_dash(self):
        info = parse_map_title('7—2珊瑚海')
        assert info is not None
        assert info.chapter == 7
        assert info.map_num == 2

    def test_invalid_text(self):
        assert parse_map_title('无效文本') is None
        assert parse_map_title('') is None
        assert parse_map_title('abc') is None

    def test_raw_text_preserved(self):
        raw = '9-5/南大洋群岛'
        info = parse_map_title(raw)
        assert info is not None
        assert info.raw_text == raw

    # ── OCR 校正测试 ──

    def test_ocr_correction_951(self):
        """OCR 读出 "9-51南大洋群岛" → 应校正为 9-5 南大洋群岛。"""
        info = parse_map_title('9-51南大洋群岛')
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        assert info.name == '南大洋群岛'

    def test_ocr_correction_911(self):
        """OCR 读出 "9-11地峡外海" → 应校正为 9-1 地峡外海。"""
        info = parse_map_title('9-11地峡外海')
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 1
        assert info.name == '地峡外海'

    def test_ocr_correction_uses_db_name(self):
        """OCR 校正后使用数据库名称。"""
        info = parse_map_title('9-51大洋群岛')
        assert info is not None
        assert info.chapter == 9
        assert info.map_num == 5
        # 使用数据库名称而非 OCR 残余
        assert info.name == '南大洋群岛'

    def test_single_digit_preferred(self):
        """单位数匹配优先于多位数 (如 "1-1" 不被拆成 "1-1")。"""
        info = parse_map_title('1-1母港附近海域')
        assert info is not None
        assert info.chapter == 1
        assert info.map_num == 1
        assert info.name == '母港附近海域'

    def test_ocr_correction_81(self):
        """OCR 读出 "8-11百慕大中心海域" → 应校正为 8-1。"""
        info = parse_map_title('8-11百慕大中心海域')
        assert info is not None
        assert info.chapter == 8
        assert info.map_num == 1
        assert info.name == '百慕大中心海域'


# ─────────────────────────────────────────────
# MAP_DATABASE 完整性
# ─────────────────────────────────────────────


class TestMapDatabase:
    def test_all_chapters_present(self):
        """数据库包含 1-10 章。"""
        chapters = {ch for ch, _ in constants.MAP_DATABASE}
        assert chapters == set(range(1, 11))

    def test_chapter_map_counts(self):
        """每章至少 1 张地图（早期章节 4+，新章节可能只有 1 张）。"""
        for ch in range(1, 11):
            assert ch in constants.CHAPTER_MAP_COUNTS
            assert constants.CHAPTER_MAP_COUNTS[ch] >= 1

    def test_known_maps(self):
        """抽检几个已知地图。"""
        assert constants.MAP_DATABASE[(1, 1)] == '母港附近海域'
        assert constants.MAP_DATABASE[(9, 5)] == '南大洋群岛'
        assert constants.MAP_DATABASE[(5, 5)] == '直布罗陀要塞'
        assert constants.MAP_DATABASE[(8, 5)] == '地峡海湾'

    def test_total_map_count(self):
        """总地图数量检查 (9章, 共 ~40+ 张)。"""
        assert len(constants.MAP_DATABASE) >= 40


class TestChapterSlots:
    @staticmethod
    def slots(values: list[int | None]) -> tuple[ChapterSlot, ...]:
        return tuple(
            ChapterSlot(index=i, chapter=chapter, text='', confidence=1.0)
            for i, chapter in enumerate(values)
        )

    def test_parse_labels_and_placeholder(self):
        assert parse_chapter_label('第六章') == 6
        assert parse_chapter_label('第10章') == 10
        assert parse_chapter_label('---') is None
        assert parse_chapter_label('3十章') is None

    def test_prefers_visible_target(self):
        slots = self.slots([8, 9, 10, None, None])
        assert _calculate_chapter_slot(10, 9, slots) == 1

    def test_uses_two_slot_jump_when_available(self):
        slots = self.slots([8, 9, 10, None, None])
        assert _calculate_chapter_slot(10, 5, slots) == 0

    def test_uses_one_slot_jump_after_overshoot(self):
        slots = self.slots([4, 5, 6, 7, 8])
        assert _calculate_chapter_slot(6, 5, slots) == 1

    def test_uses_two_slot_jump_at_lower_boundary(self):
        slots = self.slots([None, None, 1, 2, 3])
        assert _calculate_chapter_slot(1, 5, slots) == 4

    def test_refuses_placeholder_slot(self):
        slots = self.slots([None, 9, 10, None, None])
        assert _calculate_chapter_slot(10, 8, slots) is None


class TestBattlePageCalibration:
    def test_static_coordinates_keep_reference_pixels(self):
        """页面私有四位坐标在基准分辨率下保持旧校准像素。"""
        from autowsgr.common.calibration import map

        def pixels(coord: tuple[float, float]) -> tuple[int, int]:
            return int(coord[0] * 1280), int(coord[1] * 720)

        assert pixels(main_page.constants.CLICK_BACK) == pixels(map.CLICK_BACK)
        assert {
            name: pixels(coord) for name, coord in main_page.constants.TAB_POSITIONS.items()
        } == {
            'sortie': pixels(map.PANEL_POSITIONS['sortie']),
            'exercise': pixels(map.PANEL_POSITIONS['exercise']),
            'expedition': pixels(map.PANEL_POSITIONS['expedition']),
            'campaign': pixels(map.PANEL_POSITIONS['battle']),
            'decisive': pixels(map.PANEL_POSITIONS['decisive']),
        }
        assert pixels(constants.CLICK_ENTER_SORTIE) == pixels(map.CLICK_ENTER_SORTIE)
        assert pixels(decisive_page.constants.CLICK_ENTER_DECISIVE) == pixels(
            map.CLICK_ENTER_DECISIVE
        )
        assert pixels(constants.CLICK_MAP_NEXT) == pixels(map.CLICK_MAP_NEXT)
        assert pixels(constants.CLICK_MAP_PREV) == pixels(map.CLICK_MAP_PREV)
        assert pixels(expedition_page.constants.CLICK_SKIP) == pixels(map.CLICK_EXPEDITION_SKIP)


# ─────────────────────────────────────────────
# 动作 — 章节导航
# ─────────────────────────────────────────────


class TestNavigateToChapter:
    def test_invalid_chapter_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=ocr)
        pg = BattlePage(ctx)
        with pytest.raises(ValueError, match='1-10'):
            pg.select_chapter(0)
        with pytest.raises(ValueError, match='1-10'):
            pg.select_chapter(11)

    def test_no_ocr_raises(self):
        ctrl = MagicMock(spec=AndroidController)
        ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=None)
        pg = BattlePage(ctx)
        with pytest.raises(RuntimeError, match='OCR'):
            pg.select_chapter(5)

    def test_fixed_slots_navigate_by_two_then_one(self):
        ctrl = MagicMock(spec=AndroidController)
        ocr = MagicMock()
        ctx = GameContext(ctrl=ctrl, config=MagicMock(), ocr=ocr)
        pg = BattlePage(ctx)
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        ctrl.screenshot.return_value = screen

        slot_reads = [
            ['第八章', '第九章', '第十章', '---', '---'],
            ['第六章', '第七章', '第八章', '第九章', '第十章'],
            ['第四章', '第五章', '第六章', '第七章', '第八章'],
            ['第三章', '第四章', '第五章', '第六章', '第七章'],
            ['第三章', '第四章', '第五章', '第六章', '第七章'],
        ]
        ocr.recognize_single.side_effect = [
            OCRResult(text=text, confidence=0.95) for row in slot_reads for text in row
        ]
        ocr.recognize_maxlen.side_effect = [
            OCRResult(text=text, confidence=0.95) for text in ['10-1', '8-1', '6-1', '5-3', '5-3']
        ]

        with patch(
            'autowsgr.application.ui.controller.operations.sortie_page.battle_page.page.time.sleep'
        ):
            result = pg.select_chapter(5)

        assert result == 5
        assert ctrl.click.call_args_list == [
            call(0.1, 0.31),
            call(0.1, 0.31),
            call(0.1, 0.43),
        ]
