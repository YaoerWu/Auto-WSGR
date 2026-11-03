"""模块功能：验证模拟器进程管理器工厂与会话生命周期入口。

直接调用方：设备服务。

直接依赖：pytest、lifecycle.service 与各宿主管理器替身。

边界：不启动、停止或检测真实模拟器进程。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import OSType
from autowsgr.common.device.device_engine.orchestration.lifecycle import service
from autowsgr.common.device.errors import DeviceError


if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeManager:
    """记录调用的进程管理器替身。"""

    def __init__(self, name: str, calls: list[tuple[str, tuple[object, ...]]]) -> None:
        self.name = name
        self.calls = calls
        self.online = True

    def check_emulator_running(self) -> bool:
        """记录状态检查并返回预置结果。"""
        self.calls.append(('check', ()))
        return self.online

    def start_emulator(self) -> None:
        """记录启动调用。"""
        self.calls.append(('start', ()))

    def stop_emulator(self) -> None:
        """记录停止调用。"""
        self.calls.append(('stop', ()))

    def restart_emulator(self) -> None:
        """记录重启调用。"""
        self.calls.append(('restart', ()))

    def wait_for_emulator_online(self, timeout: float = 120) -> None:
        """记录上线等待的超时参数。"""
        self.calls.append(('wait', (timeout,)))


def _install_managers(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, tuple[object, ...]]], dict[str, object]]:
    """把三个宿主管理器工厂换成记录调用的替身。"""
    created: dict[str, object] = {}
    calls: list[tuple[str, tuple[object, ...]]] = []

    def factory(name: str) -> Callable[..., object]:
        def create(config: DeviceConfig, serial: str | None = None) -> _FakeManager:
            calls.append((name, (config, serial)))
            manager = _FakeManager(name, calls)
            created[name] = manager
            return manager

        return create

    for name, attribute in (
        ('windows', 'WindowsEmulatorManager'),
        ('macos', 'MacEmulatorManager'),
        ('linux', 'LinuxEmulatorManager'),
    ):
        monkeypatch.setattr(service, attribute, factory(name))
    return calls, created


@pytest.mark.parametrize(
    ('os_type', 'expected'),
    [
        (OSType.windows, 'windows'),
        (OSType.macos, 'macos'),
        (OSType.linux, 'linux'),
    ],
)
def test_factory_selects_manager_by_host_os(
    monkeypatch: pytest.MonkeyPatch,
    os_type: OSType,
    expected: str,
) -> None:
    """工厂按宿主操作系统挑选对应管理器并透传 serial。"""
    calls, _created = _install_managers(monkeypatch)
    config = DeviceConfig()

    manager = service.create_emulator_process_manager(config, os_type, serial='emulator-5554')

    assert manager.name == expected
    assert calls == [(expected, (config, 'emulator-5554'))]


def test_factory_detects_host_os_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """未提供宿主类型时先检测宿主操作系统。"""
    calls, _created = _install_managers(monkeypatch)
    monkeypatch.setattr(service, 'detect_host_operating_system', lambda: OSType.macos)

    manager = service.create_emulator_process_manager(DeviceConfig())

    assert manager.name == 'macos'
    assert calls[0][1][1] is None


def test_factory_rejects_unsupported_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """不支持的宿主操作系统直接报错。"""
    _install_managers(monkeypatch)

    with pytest.raises(DeviceError, match='不支持的操作系统: plan9'):
        service.create_emulator_process_manager(DeviceConfig(), os_type='plan9')  # type: ignore[arg-type]


def _session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    serial: str | None = None,
    calls: list[tuple[str, tuple[object, ...]]] | None = None,
) -> SimpleNamespace:
    """构造只带配置、serial 与生命周期缓存槽的会话替身。"""
    calls = calls if calls is not None else []
    manager = _FakeManager('cached', calls)
    session = SimpleNamespace(
        config=DeviceConfig(ADB_CONNECTION='127.0.0.1:5555'),
        serial=serial,
        lifecycle=None,
    )

    def create(config: DeviceConfig, _os_type: object = None, serial: str | None = None) -> object:
        manager.calls.append(('create', (config, serial)))
        return manager

    monkeypatch.setattr(service, 'create_emulator_process_manager', create)
    return session


def test_manager_is_created_once_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一会话只创建一次管理器，并把 serial 传给工厂。"""
    session = _session(monkeypatch, serial='emulator-5554')

    first = service._ensure_emulator_manager(session)
    second = service._ensure_emulator_manager(session)

    assert first is second is session.lifecycle
    assert [call for call in first.calls if call[0] == 'create'] == [
        ('create', (session.config, 'emulator-5554')),
    ]


def test_manager_falls_back_to_configured_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话尚未绑定 serial 时用配置里的 ADB 连接串。"""
    session = _session(monkeypatch)

    manager = service._ensure_emulator_manager(session)

    assert manager.calls[0] == ('create', (session.config, '127.0.0.1:5555'))


def test_lifecycle_entries_delegate_to_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """五个生命周期入口把调用与超时参数转给会话管理器。"""
    session = _session(monkeypatch)

    assert service._check_emulator_running(session) is True
    service._start_emulator(session)
    service._stop_emulator(session)
    service._restart_emulator(session)
    service._wait_for_emulator_online(session, 30)

    assert session.lifecycle.calls[1:] == [
        ('check', ()),
        ('start', ()),
        ('stop', ()),
        ('restart', ()),
        ('wait', (30,)),
    ]
