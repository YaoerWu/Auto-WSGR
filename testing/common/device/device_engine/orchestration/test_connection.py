"""模块功能：验证设备连接、断开与 ADB 重试流程的状态迁移。

直接调用方：设备服务与截图/操作编排。

直接依赖：pytest、orchestration.connection 与 scrcpy/adb 替身。

边界：不建立真实 ADB 或 scrcpy 连接。
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.orchestration import connection, discovery
from autowsgr.common.device.device_engine.orchestration.connection import DeviceInfo
from autowsgr.common.device.errors import DeviceConnectionError


class _FakeScrcpy:
    """记录连接与断开动作的串流引擎替身。"""

    def __init__(
        self,
        *,
        connected: bool = False,
        resolution: tuple[int, int] = (800, 600),
        connect_error: Exception | None = None,
    ) -> None:
        self._connected = connected
        self._resolution = resolution
        self._connect_error = connect_error
        self.operations: list[str] = []

    @property
    def resolution(self) -> tuple[int, int]:
        """返回预置分辨率。"""
        return self._resolution

    def is_scrcpy_connected(self) -> bool:
        """返回预置连接状态。"""
        return self._connected

    def connect_scrcpy(self, _adb_device: object, serial: str) -> tuple[int, int]:
        """记录连接动作，按需抛出异常。"""
        self.operations.append(f'connect:{serial}')
        if self._connect_error is not None:
            raise self._connect_error
        self._connected = True
        return self._resolution

    def disconnect_scrcpy(self) -> None:
        """记录断开动作。"""
        self.operations.append('disconnect')
        self._connected = False


def _session(scrcpy: _FakeScrcpy) -> SimpleNamespace:
    """构造只带配置和串流引擎的会话替身。"""
    return SimpleNamespace(scrcpy=scrcpy, serial=None, adb_device=None, config=DeviceConfig())


def test_connect_device_reuses_live_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """串流已连接时直接返回当前 serial 与分辨率。"""
    scrcpy = _FakeScrcpy(connected=True, resolution=(1280, 720))
    session = _session(scrcpy)
    session.serial = 'emulator-5554'

    def unexpected_resolve(_config: object) -> str:
        raise AssertionError('不应重新解析设备')

    monkeypatch.setattr(discovery, 'resolve_device_serial', unexpected_resolve)

    assert connection._connect_device(session) == DeviceInfo('emulator-5554', (1280, 720))
    assert scrcpy.operations == []


def test_connect_device_binds_adb_handle_and_clears_on_stream_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功连接绑定 adb 句柄与 serial，串流失败时不留半绑定状态。"""
    adb_device = object()
    monkeypatch.setattr(discovery, 'resolve_device_serial', lambda _config: '127.0.0.1:16384')
    monkeypatch.setattr(connection, '_connect_adb_device', lambda _serial: adb_device)
    scrcpy = _FakeScrcpy(resolution=(960, 540))
    session = _session(scrcpy)

    info = connection._connect_device(session)

    assert info == DeviceInfo('127.0.0.1:16384', (960, 540))
    assert session.adb_device is adb_device
    assert session.serial == '127.0.0.1:16384'
    assert scrcpy.operations == ['connect:127.0.0.1:16384']

    failing_scrcpy = _FakeScrcpy(connect_error=RuntimeError('stream refused'))
    failing_session = _session(failing_scrcpy)
    monkeypatch.setattr(discovery, 'resolve_device_serial', lambda _config: 'emulator-5554')

    with pytest.raises(RuntimeError, match='stream refused'):
        connection._connect_device(failing_session)

    assert failing_session.adb_device is None
    assert failing_session.serial is None


def test_disconnect_closes_stream_and_clears_binding() -> None:
    """断开时关闭串流并清空会话绑定，连接状态以串流引擎为准。"""
    scrcpy = _FakeScrcpy(connected=True)
    session = _session(scrcpy)
    session.serial = 'emulator-5554'
    session.adb_device = object()
    assert connection._is_device_connected(session) is True

    connection._disconnect_device(session)

    assert scrcpy.operations == ['disconnect']
    assert session.serial is None
    assert session.adb_device is None


def test_reconnect_device_disconnects_then_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    """重连先断开旧流，再按新 serial 重新建立。"""
    scrcpy = _FakeScrcpy(connected=True, resolution=(800, 480))
    session = _session(scrcpy)
    session.serial = 'old-serial'
    monkeypatch.setattr(discovery, 'resolve_device_serial', lambda _config: 'new-serial')
    monkeypatch.setattr(connection, '_connect_adb_device', lambda _serial: object())

    info = connection._reconnect_device(session)

    assert info == DeviceInfo('new-serial', (800, 480))
    assert scrcpy.operations == ['disconnect', 'connect:new-serial']


def test_connect_adb_device_retries_with_server_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连接失败时重启 adb server 并重试，重启失败不阻断，三次耗尽后报错。"""
    adb_device = object()
    monkeypatch.setitem(
        sys.modules,
        'adbutils',
        SimpleNamespace(adb=SimpleNamespace(device=lambda **_kwargs: adb_device)),
    )
    attempts: list[str] = []
    restarts: list[None] = []
    sleeps: list[float] = []

    def connect(serial: str) -> None:
        attempts.append(serial)
        if len(attempts) < 3:
            raise DeviceConnectionError('连接被拒绝')

    monkeypatch.setattr(connection.executor, 'connect_adb_device', connect)
    monkeypatch.setattr(connection.executor, 'restart_adb_server', lambda: restarts.append(None))
    monkeypatch.setattr(connection.time, 'sleep', sleeps.append)

    assert connection._connect_adb_device('127.0.0.1:16384') is adb_device
    assert attempts == ['127.0.0.1:16384'] * 3
    assert len(restarts) == 2
    assert sleeps == [2.0, 2.0]

    attempts.clear()
    seen: list[int] = []

    def connect_once(_serial: str) -> None:
        seen.append(1)
        if len(seen) == 1:
            raise DeviceConnectionError('连接被拒绝')

    def failing_restart() -> None:
        raise RuntimeError('adb server 无法启动')

    sleeping: list[float] = []
    monkeypatch.setattr(connection.executor, 'connect_adb_device', connect_once)
    monkeypatch.setattr(connection.executor, 'restart_adb_server', failing_restart)
    monkeypatch.setattr(connection.time, 'sleep', sleeping.append)

    assert connection._connect_adb_device('emulator-5554') is adb_device
    assert len(seen) == 2
    assert sleeping == [2.0]

    monkeypatch.setattr(
        connection.executor,
        'connect_adb_device',
        lambda _serial: (_ for _ in ()).throw(DeviceConnectionError('连接被拒绝')),
    )
    monkeypatch.setattr(connection.executor, 'restart_adb_server', lambda: None)
    monkeypatch.setattr(connection.time, 'sleep', lambda _seconds: None)

    with pytest.raises(DeviceConnectionError, match=r'连接设备失败: 127\.0\.0\.1:16384'):
        connection._connect_adb_device('127.0.0.1:16384')


def test_connect_device_resolves_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接入口把 DeviceConfig 原样交给 serial 解析。"""
    seen: list[object] = []
    config = DeviceConfig(ADB_CONNECTION='emulator-5554')

    def resolve(value: object) -> str:
        seen.append(value)
        return 'emulator-5554-2'

    monkeypatch.setattr(discovery, 'resolve_device_serial', resolve)
    monkeypatch.setattr(connection, '_connect_adb_device', lambda _serial: object())

    connection._connect_device(
        SimpleNamespace(scrcpy=_FakeScrcpy(), serial=None, adb_device=None, config=config)
    )

    assert seen == [config]
