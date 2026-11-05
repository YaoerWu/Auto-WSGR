"""模块功能：战斗模块的对外异常。

上层调用：
- application.combat 内部：识别超时、收到停止请求、流程无法继续时抛出。
- business.combat 编排层：捕获后决定重试、换图或上报。

下层依赖：无。

边界：只定义异常类型；不打印日志、不做恢复动作。
"""

from __future__ import annotations


__all__ = [
    'CombatError',
    'CombatRecognitionTimeoutError',
    'CombatStopRequestedError',
]


class CombatError(Exception):
    """战斗模块所有异常的基类。"""


class CombatRecognitionTimeoutError(CombatError):
    """在限定次数内没有识别到预期阶段。"""


class CombatStopRequestedError(CombatError):
    """调用方请求停止战斗。"""
