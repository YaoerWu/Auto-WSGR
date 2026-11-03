"""模块功能：验证舰名纠错规则与模糊匹配的容错边界。

直接调用方：项目测试运行器。

直接依赖：fleet_select.rules.shipnames 与 fleet_select.operation.ship_select 的搜索词规则。

边界：只验证纯文本规则，不读截图、不读页面。
"""

from __future__ import annotations

import pytest

from autowsgr.application.fleet_select.operation.ship_select import _get_search_keyword
from autowsgr.application.fleet_select.rules.shipnames import (
    apply_ship_name_aliases,
    correct_ship_name,
    select_ship_name,
)
from autowsgr.application.fleet_select.types import ShipSelector


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
    assert correct_ship_name(raw_text) == expected


def test_apply_corrections_turns_leading_zero_into_submarine_prefix() -> None:
    """潜艇编号的 U 被读成 0 时补回 U，缺的横杠留给舰名表模糊匹配补。"""
    assert correct_ship_name('01206') == 'U1206'
    assert select_ship_name('U1206', ['U-1206']) == 'U-1206'


def test_apply_corrections_keeps_short_numeric_text() -> None:
    """数字不足三位时不足以判定是潜艇编号，保持原样。"""
    assert correct_ship_name('012') != 'U-12'
    assert correct_ship_name('01') == '01'


def test_apply_corrections_turns_cjk_colon_into_separator() -> None:
    """两个汉字之间的冒号是间隔号的误读。"""
    assert correct_ship_name('企业:改') == '企业·改'


def test_fuzzy_match_returns_exact_candidate() -> None:
    """完全一致时直接返回候选本身。"""
    assert select_ship_name('企业', ['企业']) == '企业'


def test_fuzzy_match_tolerates_one_extra_character() -> None:
    """短舰名只容忍一个字符的差异，比如多读了一个「号」。"""
    assert select_ship_name('企业号', ['企业']) == '企业'


def test_fuzzy_match_rejects_single_character_typo() -> None:
    """单字输入不参与容错，避免任何短词都凑上一个舰名。"""
    assert select_ship_name('企', ['企业']) is None


def test_fuzzy_match_returns_none_when_nearest_candidates_tie() -> None:
    """最近的两个候选距离相同时不猜，返回空。"""
    assert select_ship_name('ABC', ['ABD', 'ABE']) is None


def test_fuzzy_match_returns_none_for_empty_input() -> None:
    """没有文本或没有候选时不匹配。"""
    assert select_ship_name('', ['企业']) is None
    assert select_ship_name('企业', []) is None


def test_search_keyword_uses_display_name_inside_alias_scope() -> None:
    """配置映射生效时，搜索框里用游戏内显示名而不是图鉴标准名。"""
    with apply_ship_name_aliases({'希尔德布兰德': 'AIII'}):
        assert _get_search_keyword(ShipSelector('AIII')) == '希尔德布兰德'


def test_search_keyword_keeps_original_name_without_alias() -> None:
    """没有映射时不改写搜索词。"""
    assert _get_search_keyword(ShipSelector('AIII')) == 'AIII'
    assert _get_search_keyword(ShipSelector('新奥尔良')) == '新奥尔良'
