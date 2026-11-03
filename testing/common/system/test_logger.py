"""模块功能：验证日志通道绑定、北京时间、级别筛选与文件输出。

直接调用方：项目测试运行器。

直接依赖：pytest、loguru、autowsgr.common.system.logger 与 config。

边界：初始化日志时只写临时目录，结束后移除 sink，避免影响其他用例。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from loguru import logger as loguru_logger

from autowsgr.common.system import logger as logger_module
from autowsgr.common.system.config import LogConfig
from autowsgr.common.system.logger import get_logger, setup_logger


def _record(level_name: str, number: int, channel: str) -> dict:
    """构造筛选器需要的最小日志记录。"""
    return {
        'level': SimpleNamespace(name=level_name, no=number),
        'extra': {'ch': channel},
    }


def test_get_logger_returns_channel_bound_logger() -> None:
    """日志对象可按模块通道创建，并保留常用输出方法。"""
    bound = get_logger('vision.pixel')
    assert bound is not loguru_logger
    for method_name in ('debug', 'info', 'warning', 'error'):
        assert callable(getattr(bound, method_name))


def test_src_patcher_uses_beijing_time_and_relative_source() -> None:
    """记录时间转为北京时间，项目内路径相对项目根输出，项目外只留文件名。"""
    source = logger_module._PROJECT_ROOT / 'autowsgr' / 'common' / 'system' / 'logger.py'
    record = {
        'time': datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        'file': SimpleNamespace(path=str(source), name='logger.py'),
        'line': 42,
        'extra': {},
    }

    logger_module._src_patcher(record)

    assert record['time'].hour == 8
    assert record['time'].utcoffset() == timedelta(hours=8)
    assert record['extra']['src'] == 'autowsgr/common/system/logger.py:42'
    assert record['extra']['ch'] == ''

    outside = {
        'time': datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        'file': SimpleNamespace(path=str(Path('/outside/script.py')), name='script.py'),
        'line': 7,
        'extra': {'ch': 'combat'},
    }

    logger_module._src_patcher(outside)

    assert outside['extra']['src'] == 'script.py:7'
    assert outside['extra']['ch'] == 'combat'


def test_open_debug_channels_and_filter_rules() -> None:
    """打开的 LOG_*_OPEN 开关转成小写通道前缀，筛选器按级别与通道放行。"""
    assert logger_module._open_debug_channels(LogConfig()) == frozenset()
    assert logger_module._open_debug_channels(LogConfig(LOG_COMBAT_OPEN=True)) == {'combat'}

    dropped = logger_module._make_filter(10, frozenset({'combat'}))
    assert dropped(_record('TRACE', 5, 'combat')) is False
    assert dropped(_record('SUCCESS', 25, 'combat')) is False

    debug_filter = logger_module._make_filter(20, frozenset({'combat'}))
    assert debug_filter(_record('DEBUG', 10, 'combat')) is True
    assert debug_filter(_record('DEBUG', 10, 'combat.sortie')) is True
    assert debug_filter(_record('DEBUG', 10, 'Combat')) is True
    assert debug_filter(_record('DEBUG', 10, 'ui')) is False
    assert debug_filter(_record('DEBUG', 10, 'combatx')) is False
    assert debug_filter(_record('DEBUG', 10, '')) is False

    normal_filter = logger_module._make_filter(20, frozenset())
    assert normal_filter(_record('INFO', 20, '')) is True
    assert normal_filter(_record('WARNING', 30, '')) is True
    assert normal_filter(_record('DEBUG', 10, '')) is False


def test_setup_logger_creates_file_and_filters_debug(tmp_path: Path) -> None:
    """初始化后创建日志目录，并按通道筛选 DEBUG 输出。"""
    log_dir = tmp_path / 'logs'
    setup_logger(LogConfig(LOG_LEVEL='INFO', LOG_USER_DIR=log_dir, LOG_COMBAT_OPEN=True))
    try:
        get_logger('combat').debug('战斗调试')
        get_logger('ui').debug('界面调试')
        get_logger('combat').info('战斗信息')
        loguru_logger.complete()
    finally:
        loguru_logger.remove()

    assert log_dir.is_dir()
    log_files = list(log_dir.glob('*.log'))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding='utf-8')
    assert '战斗调试' in content
    assert '界面调试' not in content
    assert '战斗信息' in content
