"""验证 common/system 的公开出口。

直接调用方：项目测试运行器。

直接依赖：autowsgr.common.system 及其子模块。

边界：只检查导出名单与模块同一性，不初始化日志、不写文件。
"""

from __future__ import annotations

from autowsgr.common import system
from autowsgr.common.system import enums, errors, files, logger


def test_system_exposes_only_capability_namespaces() -> None:
    """包只导出四个基础设施模块，旧顶层函数不再存在。"""
    assert system.__all__ == ['enums', 'errors', 'files', 'logger']
    assert system.enums is enums
    assert system.errors is errors
    assert system.files is files
    assert system.logger is logger
    for legacy in ('load_yaml', 'merge_dicts', 'save_image', 'AutoWSGRError'):
        assert not hasattr(system, legacy)
        assert not hasattr(system.errors, legacy)
