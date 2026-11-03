"""验证 DeviceConfig 的默认值、取值范围与严格字段约束。

直接调用方：设备服务与生命周期工厂通过 DeviceConfig 读取配置。
直接依赖：pydantic 的 BaseModel 校验。
边界：只做模型层校验，不建立任何设备连接。
"""

import pytest
from pydantic import ValidationError

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType


def test_default_values() -> None:
    """未显式传参时使用默认串流参数与雷电模拟器类型。"""
    config = DeviceConfig()

    assert config.ADB_CONNECTION is None
    assert config.SCRCPY_MAX_SIZE == 0
    assert config.SCRCPY_BITRATE == 8_000_000
    assert config.SCRCPY_MAX_FPS == 0
    assert config.SCRCPY_SCREENSHOT_TIMEOUT == 10.0
    assert config.DEVICE_EMULATOR_TYPE is EmulatorType.leidian
    assert config.DEVICE_EMULATOR_PATH is None
    assert config.DEVICE_OPERATION_DELAY_MIN == 0.0
    assert config.DEVICE_OPERATION_DELAY_MAX == 0.0


def test_unknown_field_is_rejected() -> None:
    """未声明字段被 extra=forbid 拒绝，避免拼错配置键后静默生效。"""
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        DeviceConfig(ADB_CONNECTIONS='127.0.0.1:16384')


@pytest.mark.parametrize(
    ('field_name', 'value'),
    [
        ('SCRCPY_MAX_SIZE', -1),
        ('SCRCPY_BITRATE', 0),
        ('SCRCPY_MAX_FPS', -1),
        ('SCRCPY_SCREENSHOT_TIMEOUT', 0.0),
        ('DEVICE_OPERATION_DELAY_MIN', -0.1),
        ('DEVICE_OPERATION_DELAY_MAX', -0.1),
    ],
)
def test_out_of_range_values_are_rejected(field_name: str, value: float) -> None:
    """各数值字段遵守声明中的边界约束。"""
    with pytest.raises(ValidationError):
        DeviceConfig(**{field_name: value})


def test_model_is_frozen() -> None:
    """配置对象不可变，避免运行期被意外改写。"""
    config = DeviceConfig()

    with pytest.raises(ValidationError):
        config.SCRCPY_BITRATE = 1
