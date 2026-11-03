"""模块功能：定义换船模块的可覆盖配置。

上层调用：
- autowsgr.config：把换船配置聚合进顶层用户配置。

下层依赖：
- Pydantic：提供字段校验和不可变模型。
- common.system.config：提供模块配置基类。
- common.system.logger：记录被跳过的格式错误条目。

边界：只保存舰名映射，不读取文件、不访问 OCR 引擎、不操作设备。
"""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from autowsgr.common.system.config import ModuleConfig
from autowsgr.common.system.logger import get_logger


_log = get_logger('infra')

# 舰名映射行允许的冒号写法。
_NAME_SEPARATORS = (':', '：')
# 同一艘船的多个自定义名之间的分隔符。
_ALIAS_SEPARATOR_PATTERN = re.compile('[,，]')


class FleetSelectConfig(ModuleConfig):
    """保存换船模块的可覆盖配置。"""

    SHIP_NAME_MAP: dict[str, str] = Field(default_factory=dict)  # 系统标准船名 -> 游戏内显示船名。

    @field_validator('SHIP_NAME_MAP', mode='before')
    @classmethod
    def _parse_ship_name_map(cls, value: object) -> dict[str, str]:
        """把映射或多行文本归一成系统标准船名到游戏内显示船名的映射。"""
        if value is None:
            return {}
        if isinstance(value, str):
            return _parse_ship_name_text(value)
        if not isinstance(value, dict):
            _log.warning('FLEET_SELECT.SHIP_NAME_MAP 必须是映射或多行文本，已忽略该配置')
            return {}

        names: dict[str, str] = {}
        for raw_system_name, raw_display_name in value.items():
            system_name = str(raw_system_name).strip()
            display_name = str(raw_display_name).strip()
            if not system_name or not display_name:
                continue
            _reject_duplicate_display_name(names, system_name, display_name)
            names[system_name] = display_name
        return names


def _parse_ship_name_text(text: str) -> dict[str, str]:
    """按行解析“系统舰名: 游戏内舰名”，冒号两侧的空格和中文冒号都接受。

    一艘标准舰名只能对应一个游戏内舰名，一个游戏内舰名也只能对应一艘标准舰名。
    """
    names: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        separator = next((item for item in _NAME_SEPARATORS if item in line), None)
        if separator is None:
            _log.warning('跳过缺少冒号的舰名映射: {}', line)
            continue
        system_name, display_name = (part.strip() for part in line.split(separator, 1))
        if not system_name or not display_name:
            continue
        if _ALIAS_SEPARATOR_PATTERN.search(display_name):
            raise ValueError(
                f'一艘标准舰名只能对应一个游戏内舰名，{line!r} 写了多个；一行只写一艘船。',
            )
        _reject_duplicate_display_name(names, system_name, display_name)
        names[system_name] = display_name
    return names


def _reject_duplicate_display_name(
    names: dict[str, str],
    system_name: str,
    display_name: str,
) -> None:
    """同一个游戏内舰名被两艘标准舰名占用时抛错，避免搜索时分不清目标。"""
    for existing_system_name, existing_display_name in names.items():
        if existing_display_name == display_name:
            raise ValueError(
                f'游戏内舰名 {display_name!r} 同时映射自 {existing_system_name!r} 和 '
                f'{system_name!r}；同一艘船只能有一个游戏内舰名。',
            )


__all__ = ['FleetSelectConfig']
