"""模块功能：验证日志配置的默认值、不可变性与字段校验。

直接调用方：项目测试运行器。

直接依赖：pytest、pydantic、autowsgr.common.system.config。

边界：只构造配置对象，不初始化日志输出、不写文件。
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from autowsgr.common.system.config import LOG_TIMEZONE, LogConfig


def test_timezone_and_default_values() -> None:
    """日志时区固定为东八区，默认给出调试级别、七天保留与关闭的战斗开关。"""
    assert LOG_TIMEZONE.utcoffset(None) == timedelta(hours=8)
    assert LOG_TIMEZONE.tzname(None) == 'Asia/Shanghai'

    config = LogConfig()
    assert config.LOG_LEVEL == 'DEBUG'
    assert Path('logs') == config.LOG_SYSTEM_DIR
    assert config.LOG_ROTATION == '10 MB'
    assert config.LOG_RETENTION == '7 days'
    assert config.LOG_COMBAT_OPEN is False


def test_user_directory_defaults_and_explicit_override(tmp_path: Path) -> None:
    """用户目录默认按北京时间生成时间戳子目录，显式传入时原样保留。"""
    config = LogConfig()
    user_dir = config.LOG_USER_DIR
    assert user_dir is not None
    assert user_dir.parent == config.LOG_SYSTEM_DIR
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', user_dir.name)

    target = tmp_path / 'logs'
    assert target == LogConfig(LOG_USER_DIR=target).LOG_USER_DIR


def test_validation_rejects_unknown_fields_levels_and_mutation(tmp_path: Path) -> None:
    """未知字段、非法级别与创建后修改都被拒绝。"""
    with pytest.raises(ValidationError, match='channels'):
        LogConfig(channels=('combat',))
    with pytest.raises(ValidationError, match='LOG_LEVEL'):
        LogConfig(LOG_LEVEL='TRACE')

    config = LogConfig(LOG_USER_DIR=tmp_path / 'logs')
    with pytest.raises(ValidationError):
        config.LOG_LEVEL = 'INFO'


def test_owner_prefixed_fields_are_accepted(tmp_path: Path) -> None:
    """LOG_* 前缀字段按所属模块归位。"""
    config = LogConfig.model_validate(
        {
            'LOG_LEVEL': 'INFO',
            'LOG_SYSTEM_DIR': tmp_path,
            'LOG_COMBAT_OPEN': True,
        },
    )

    assert config.LOG_LEVEL == 'INFO'
    assert config.LOG_USER_DIR is not None
    assert config.LOG_COMBAT_OPEN
    with pytest.raises(ValueError, match='LOG_LEVEL'):
        LogConfig(LOG_LEVEL='CRITICAL')
    with pytest.raises(ValueError, match='channels'):
        LogConfig.model_validate({'channels': {'combat': 'DEBUG'}})
