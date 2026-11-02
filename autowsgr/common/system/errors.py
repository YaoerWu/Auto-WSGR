"""模块功能：程序级错误基类。

这些类型只提供稳定的捕获边界，不实现具体业务行为；具体错误由所属模块定义，并决定
构造参数和错误文本。

上层调用：
- application.errors、application.navigation.types、business.combat.decisive.chapter
  和 dispatch.context.errors：继承这些基类表达应用、业务和调度错误。
- common.device.errors：继承 CommonError 表达设备错误。

下层依赖：
- Python 内置异常类型。

边界：不定义设备、视觉、页面、导航、战斗或任务的具体错误。
"""

from __future__ import annotations


class SystemError(Exception):
    """所有程序错误的共同根类。"""


class CommonError(SystemError):
    """设备、视觉和配置等公共基础能力错误。"""


class ApplicationError(SystemError):
    """应用层导航、页面和上下文控制错误。"""


class BusinessError(SystemError):
    """战斗、后勤及其他业务控制错误。"""


class DispatchError(SystemError):
    """处理器和任务调度错误。"""


__all__ = [
    'ApplicationError',
    'BusinessError',
    'CommonError',
    'DispatchError',
    'SystemError',
]
