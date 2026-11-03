"""模块功能：验证模拟器进程管理器的重启顺序与上线等待。

直接调用方：生命周期服务与各宿主实现。

直接依赖：pytest、lifecycle.base 与时钟替身。

边界：不启动或停止真实模拟器。
"""

from __future__ import annotations

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.orchestration.lifecycle import base
from autowsgr.common.device.errors import DeviceError


class _FakeManager(base.EmulatorProcessManager):
    """按预置序列返回运行状态并记录动作的进程管理器替身。"""

    def __init__(self, config: DeviceConfig, checks: list[bool] | None = None) -> None:
        super().__init__(config, serial='emulator-5554')
        self.checks = list(checks or [])
        self.calls: list[str] = []

    def check_emulator_running(self) -> bool:
        """按序返回运行状态。"""
        self.calls.append('check')
        return self.checks.pop(0) if self.checks else False

    def start_emulator(self) -> None:
        """记录启动动作。"""
        self.calls.append('start')

    def stop_emulator(self) -> None:
        """记录停止动作。"""
        self.calls.append('stop')


def _config() -> DeviceConfig:
    """返回带模拟器路径的配置。"""
    return DeviceConfig(DEVICE_EMULATOR_PATH='C:/emulator/dnplayer.exe')


def test_manager_keeps_process_name_and_serial() -> None:
    """管理器保留模拟器进程名与绑定的 serial。"""
    manager = _FakeManager(_config())

    assert manager._process_name == 'dnplayer.exe'
    assert manager._serial == 'emulator-5554'


def test_manager_is_abstract() -> None:
    """缺少宿主实现时不能直接实例化抽象基类。"""
    with pytest.raises(TypeError):
        base.EmulatorProcessManager(_config())


def test_restart_stops_then_starts() -> None:
    """重启顺序是先停止再启动。"""
    manager = _FakeManager(_config())

    manager.restart_emulator()

    assert manager.calls == ['stop', 'start']


def test_wait_returns_once_online(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动过程中轮询到在线即返回，每次轮询间隔一秒。"""
    manager = _FakeManager(_config(), checks=[False, True])
    sleeps: list[float] = []
    monkeypatch.setattr(base.time, 'sleep', sleeps.append)

    manager.wait_for_emulator_online(timeout=30)

    assert manager.calls == ['check', 'check']
    assert sleeps == [1.0]


def test_wait_raises_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时仍未上线时抛出带超时秒数的错误。"""
    manager = _FakeManager(_config(), checks=[False])
    monkeypatch.setattr(base.time, 'monotonic', iter([0.0, 100.0]).__next__)
    sleeps: list[float] = []
    monkeypatch.setattr(base.time, 'sleep', sleeps.append)

    with pytest.raises(DeviceError, match='模拟器启动超时 \\(10s\\)'):
        manager.wait_for_emulator_online(timeout=10)

    assert sleeps == []
