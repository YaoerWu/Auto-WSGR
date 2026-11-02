"""模块功能：验证舰名纠错规则与模糊匹配的容错边界。

直接调用方：项目测试运行器。

直接依赖：fleet_select.names。

边界：只验证纯文本规则，不读截图、不读页面。
"""

from __future__ import annotations

import pytest

from autowsgr.application.fleet_select.names import (
    apply_ship_name_corrections,
    fuzzy_match_ship_name,
)


@pytest.mark.parametrize(
    ('raw_text', 'expected'),
    [
        ('鲍鱼', '鲃鱼'),
        ('鳟盹', '鳞鲀'),
        ('296', 'M-296'),
        ('维内托', '维托里奥·维内托'),
        ('IA', 'IIIA'),
    ],
)
def test_apply_corrections_returns_standard_name(raw_text: str, expected: str) -> None:
    """命中已知错字时直接换成标准舰名。"""
    assert apply_ship_name_corrections(raw_text) == expected


def test_apply_corrections_turns_leading_zero_into_submarine_prefix() -> None:
    """潜艇编号的 U 被读成 0 时补回 U，缺的横杠留给舰名表模糊匹配补。"""
    assert apply_ship_name_corrections('01206') == 'U1206'
    assert fuzzy_match_ship_name('U1206', ['U-1206']) == 'U-1206'


def test_apply_corrections_keeps_short_numeric_text() -> None:
    """数字不足三位时不足以判定是潜艇编号，保持原样。"""
    assert apply_ship_name_corrections('012') != 'U-12'
    assert apply_ship_name_corrections('01') == '01'


def test_apply_corrections_turns_cjk_colon_into_separator() -> None:
    """两个汉字之间的冒号是间隔号的误读。"""
    assert apply_ship_name_corrections('企业:改') == '企业·改'


def test_fuzzy_match_returns_exact_candidate() -> None:
    """完全一致时直接返回候选本身。"""
    assert fuzzy_match_ship_name('企业', ['企业']) == '企业'


def test_fuzzy_match_tolerates_one_extra_character() -> None:
    """短舰名只容忍一个字符的差异，比如多读了一个「号」。"""
    assert fuzzy_match_ship_name('企业号', ['企业']) == '企业'


def test_fuzzy_match_rejects_single_character_typo() -> None:
    """单字输入不参与容错，避免任何短词都凑上一个舰名。"""
    assert fuzzy_match_ship_name('企', ['企业']) is None


def test_fuzzy_match_returns_none_when_nearest_candidates_tie() -> None:
    """最近的两个候选距离相同时不猜，返回空。"""
    assert fuzzy_match_ship_name('ABC', ['ABD', 'ABE']) is None


def test_fuzzy_match_returns_none_for_empty_input() -> None:
    """没有文本或没有候选时不匹配。"""
    assert fuzzy_match_ship_name('', ['企业']) is None
    assert fuzzy_match_ship_name('企业', []) is None
