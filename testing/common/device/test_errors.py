"""验证设备层错误类型的继承关系与导出清单。

直接调用方：设备服务、ADB 执行器与生命周期模块抛出这些异常。
直接依赖：common.system.errors 的 CommonError 根类型。
边界：只检查类型关系，不触发真实错误路径。
"""

from autowsgr.common.device import errors
from autowsgr.common.system.errors import CommonError


def test_error_hierarchy() -> None:
    """设备错误挂在 CommonError 之下，游戏错误再挂在设备错误之下。"""
    assert errors.DeviceError.__bases__ == (CommonError,)
    assert errors.DeviceConnectionError.__bases__ == (errors.DeviceError,)
    assert errors.DeviceNotFoundError.__bases__ == (errors.DeviceError,)
    assert errors.GameError.__bases__ == (errors.DeviceError,)
    assert errors.NetworkError.__bases__ == (errors.GameError,)
    assert errors.ResourceError.__bases__ == (errors.GameError,)


def test_public_error_exports() -> None:
    """模块公开六个错误类型。"""
    assert set(errors.__all__) == {
        'DeviceConnectionError',
        'DeviceError',
        'DeviceNotFoundError',
        'GameError',
        'NetworkError',
        'ResourceError',
    }
