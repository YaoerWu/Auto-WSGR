"""模块功能：通用枚举基类。

上层调用：
- application.navigation.types、application.controller.types、application.combat.types、
  business.combat.types：按领域语义继承这些基类。
- common.device.device_engine.foundation.platform 和 common.vision.adapters.text_recognition：
  定义设备类型和识别模式枚举。

下层依赖：
- Python 标准库 enum。

边界：不定义具体业务枚举成员，不保存可变配置。
"""

from __future__ import annotations

from enum import Enum


class BaseEnum(Enum):
    """提供统一的中文非法值错误。"""

    @classmethod
    def _missing_(cls, value: object) -> None:
        """为非法枚举值生成包含支持值的错误。"""
        supported = ', '.join(str(member.value) for member in cls)
        raise ValueError(f'"{value}" 不是合法的 {cls.__name__} 取值。 支持: [{supported}]')


class StrEnum(str, BaseEnum):
    """字符串枚举基类。"""


class IntEnum(int, BaseEnum):
    """整数枚举基类。"""


__all__ = ['BaseEnum', 'IntEnum', 'StrEnum']
