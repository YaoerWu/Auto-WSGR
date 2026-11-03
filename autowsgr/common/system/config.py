"""模块功能：统一配置模型。

上层调用：
- common.system.logger：读取 LogConfig 初始化日志输出，并引用 LOG_TIMEZONE。
- 顶层配置入口：构造日志配置并传给 setup_logger。

下层依赖：
- Pydantic：提供字段校验和不可变模型。
- Python 标准库 datetime 和 pathlib。

边界：只保存配置值，不读取用户文件，不执行日志或文件操作。
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator


# 日志记录和目录命名统一使用北京时间，不随运行主机的时区变化。
LOG_TIMEZONE = datetime.timezone(datetime.timedelta(hours=8), name='Asia/Shanghai')


class ModuleConfig(BaseModel):
    """模块配置基类：不可变，且拒绝未声明的字段。"""

    model_config = {'frozen': True, 'extra': 'forbid'}


class LogConfig(ModuleConfig):
    """保存日志能力的可覆盖配置。"""

    LOG_LEVEL: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'DEBUG'  # 普通日志的最低输出级别。
    LOG_SYSTEM_DIR: Path = Path('logs')  # 未指定用户目录时使用的日志根目录。
    LOG_USER_DIR: Path | None = None  # 用户指定的日志目录；为空时由系统目录和时间生成。
    LOG_ROTATION: str = '10 MB'  # 单个日志文件达到该大小后切分。
    LOG_RETENTION: str = '7 days'  # 日志文件的保留周期，由文件 sink 执行清理。
    LOG_COMBAT_OPEN: bool = False  # 是否放行 combat 及其子通道的 DEBUG 日志。

    @model_validator(mode='after')
    def _set_log_user_dir(self) -> LogConfig:
        """为未指定目录的配置生成按北京时间命名的日志目录。"""
        if self.LOG_USER_DIR is None:
            timestamp = datetime.datetime.now(tz=LOG_TIMEZONE).strftime('%Y-%m-%d_%H-%M-%S')
            object.__setattr__(self, 'LOG_USER_DIR', self.LOG_SYSTEM_DIR / timestamp)
        return self


__all__ = ['LOG_TIMEZONE', 'LogConfig', 'ModuleConfig']
