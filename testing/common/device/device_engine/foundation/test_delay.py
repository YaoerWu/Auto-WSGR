"""验证设备操作延迟的全局配置与随机取样边界。

直接调用方：ScrcpyEngine 在 click/swipe 等操作前取样延迟。
直接依赖：random.uniform 与模块级 _operation_delay_bounds。
边界：只测配置与取值范围，不涉及真实输入事件。
"""

import math

import pytest

from autowsgr.common.device.device_engine.foundation import delay as delay_module


@pytest.fixture(autouse=True)
def _restore_delay_bounds() -> object:
    """每个用例结束后恢复模块级延迟边界，避免用例间互相污染。"""
    original = list(delay_module._operation_delay_bounds)
    yield
    delay_module._operation_delay_bounds[:] = original


def test_fixed_bounds_return_the_same_delay() -> None:
    """上下界相同时延迟恒定。"""
    delay_module.configure_operation_delay_bounds(0.2, 0.2)

    assert delay_module.calculate_operation_delay() == 0.2


def test_delay_stays_within_configured_range() -> None:
    """取样结果落在配置区间内。"""
    delay_module.configure_operation_delay_bounds(0.1, 0.3)

    for _ in range(20):
        assert 0.1 <= delay_module.calculate_operation_delay() <= 0.3


@pytest.mark.parametrize(
    ('minimum', 'maximum'),
    [
        (0.5, 0.2),
        (-0.1, 0.0),
    ],
)
def test_invalid_range_is_rejected(minimum: float, maximum: float) -> None:
    """负下界或反序区间直接拒绝。"""
    with pytest.raises(ValueError, match='设备操作延迟范围必须满足 0 <= minimum <= maximum'):
        delay_module.configure_operation_delay_bounds(minimum, maximum)


@pytest.mark.parametrize('value', [math.nan, math.inf])
def test_non_finite_bounds_are_rejected(value: float) -> None:
    """非有限数无法用于取样，直接拒绝。"""
    with pytest.raises(ValueError, match='设备操作延迟必须是有限数'):
        delay_module.configure_operation_delay_bounds(value, 0.0)
