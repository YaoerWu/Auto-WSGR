"""验证 DeviceSession 的初始化与设备句柄前置校验。

直接调用方：DeviceService 与各 orchestration 子模块共享同一会话对象。
直接依赖：ScrcpyEngine、DeviceConfig、DeviceConnectionError。
边界：不建立真实 ADB 连接，只校验会话状态机。
"""

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.session import DeviceSession
from autowsgr.common.device.errors import DeviceConnectionError


def test_session_starts_disconnected_with_scrcpy_engine() -> None:
    """新建会话时未连接设备，串流引擎已就绪但分辨率为零。"""
    session = DeviceSession(DeviceConfig())

    assert session.serial is None
    assert session.adb_device is None
    assert session.lifecycle is None
    assert session.scrcpy.resolution == (0, 0)
    assert session.scrcpy.is_scrcpy_connected() is False


def test_require_adb_device_rejects_disconnected_session() -> None:
    """未连接时访问 adb 句柄给出明确的连接提示。"""
    session = DeviceSession(DeviceConfig())

    with pytest.raises(
        DeviceConnectionError, match=r'设备未连接，请先调用 device\.service\.connect'
    ):
        session._require_adb_device()


def test_require_adb_device_returns_bound_handle() -> None:
    """已绑定的 adb 句柄原样返回。"""
    session = DeviceSession(DeviceConfig())
    adb_device = object()
    session.adb_device = adb_device

    assert session._require_adb_device() is adb_device
