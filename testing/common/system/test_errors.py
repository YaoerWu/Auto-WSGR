"""验证 common/system/errors 的程序层异常层级。

直接调用方：项目测试运行器。

直接依赖：system.errors 与 device.errors。

边界：只检查类型层级与导出名单，不抛真实业务异常。
"""

from __future__ import annotations

from autowsgr.common.device.errors import GameError, NetworkError, ResourceError
from autowsgr.common.system import errors
from autowsgr.common.system.errors import (
    ApplicationError,
    BusinessError,
    CommonError,
    DispatchError,
    SystemError,
)


def test_errors_form_the_program_layer_hierarchy() -> None:
    """异常根类型直接继承 Exception，四个一级分类挂在它下面。"""
    assert SystemError.__bases__ == (Exception,)
    for error_type in (CommonError, ApplicationError, BusinessError, DispatchError):
        assert error_type.__bases__ == (SystemError,)

    assert set(errors.__all__) == {
        'SystemError',
        'CommonError',
        'ApplicationError',
        'BusinessError',
        'DispatchError',
    }
    assert len(errors.__all__) == 5
    assert errors.SystemError is SystemError


def test_device_owns_game_error_categories() -> None:
    """游戏错误分类由 device 拥有，并挂在公共异常下。"""
    assert issubclass(GameError, CommonError)
    assert issubclass(NetworkError, GameError)
    assert issubclass(ResourceError, GameError)
