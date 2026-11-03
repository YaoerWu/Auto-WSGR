"""模块功能：维护识别文字形态与舰名匹配阈值。

上层调用：
- fleet_select.rules.ocr：剥国籍括号、归一等级形近字、匹配舰名。

下层依赖：
- 无。

边界：只保存识别规则常量，不保存流程节奏，不保存运行时状态。
"""

from __future__ import annotations


# ── 舰名匹配 ────────────────────────────────────────────────────────────────

SHIP_FUZZY_THRESHOLD = 2  # 准备页舰名在完整舰名表里允许的最大编辑距离。
CONTEXT_MATCH_THRESHOLD = 3  # 舰名在目标池里补救匹配时允许的最大编辑距离。


# ── 识别文字形态 ────────────────────────────────────────────────────────────

# 舰种文字里可能带的国籍括号，例如「轻母(U国)」；匹配枚举值前先剥掉。
COUNTRY_SUFFIX_PATTERN = r'\s*[（(][^（）()]*[)）]\s*$'

# 等级号码可能被认成的形近字母，按旧框架的映射换成数字。
LEVEL_DIGIT_TRANSLATION = {
    'I': '1',
    'i': '1',
    'l': '1',
    'L': '1',
    'O': '0',
    'o': '0',
    'D': '0',
    'd': '0',
    'S': '5',
    's': '5',
    'B': '8',
    'b': '8',
}

# 舰船等级的合法区间；超出区间的识别结果视为噪声。
LEVEL_MIN = 1
LEVEL_MAX = 110


__all__ = [
    'CONTEXT_MATCH_THRESHOLD',
    'COUNTRY_SUFFIX_PATTERN',
    'LEVEL_DIGIT_TRANSLATION',
    'LEVEL_MAX',
    'LEVEL_MIN',
    'SHIP_FUZZY_THRESHOLD',
]
