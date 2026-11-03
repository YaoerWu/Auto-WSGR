"""验证 common/system/enums 的中文枚举基类语义。

直接调用方：项目测试运行器。

直接依赖：enums.BaseEnum / StrEnum / IntEnum。

边界：只检查枚举行为，不读取配置文件或日志。
"""

from __future__ import annotations

import re

import pytest

from autowsgr.common.system.enums import BaseEnum, IntEnum, StrEnum


class _Mode(StrEnum):
    """字符串枚举样例。"""

    FIRST = 'first'
    SECOND = 'second'


class _Level(IntEnum):
    """整数枚举样例。"""

    LOW = 1
    HIGH = 2


class _Plain(BaseEnum):
    """普通枚举样例。"""

    LEFT = 'left'
    RIGHT = 'right'


def test_enums_keep_common_base_semantics() -> None:
    """字符串与整数枚举保持原生比较语义，非法取值报出全部受支持成员。"""
    assert _Mode('first') is _Mode.FIRST
    assert _Mode.FIRST == 'first'
    assert isinstance(_Mode.FIRST, str)
    assert _Level(2) is _Level.HIGH
    assert _Level.HIGH == 2
    assert isinstance(_Level.HIGH, int)
    assert issubclass(_Mode, BaseEnum)

    cases = [
        (_Mode, 'third', '"third" 不是合法的 _Mode 取值。 支持: [first, second]'),
        (_Level, 3, '"3" 不是合法的 _Level 取值。 支持: [1, 2]'),
        (_Plain, 'up', '"up" 不是合法的 _Plain 取值。 支持: [left, right]'),
    ]
    for enum_type, value, message in cases:
        with pytest.raises(ValueError, match=re.escape(message)) as error:
            enum_type(value)
        assert str(error.value) == message
