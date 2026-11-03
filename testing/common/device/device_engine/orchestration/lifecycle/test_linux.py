"""模块功能：验证 Linux/WSL 宿主模拟器管理器的状态探测与启停流程。

用替身替换 WSL 探测、ADB 查询与 subprocess，不执行真实宿主命令。
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType
from autowsgr.common.device.device_engine.orchestration.lifecycle import linux
from autowsgr.common.device.device_engine.orchestration.lifecycle.linux import (
    LinuxEmulatorManager,
)
from autowsgr.common.device.errors import DeviceError, DeviceNotFoundError


if TYPE_CHECKING:
    import pathlib


class _FakeResult:
    """记录 subprocess.run 返回值的最小替身。"""

    def __init__(self, returncode: int = 0, stdout: str = '', stderr: str = '') -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _manager(
    tmp_path: pathlib.Path,
    *,
    wsl: bool = False,
    serial: str | None = 'emulator-5554',
    path: str | None = None,
    emulator_type: EmulatorType = EmulatorType.others,
) -> LinuxEmulatorManager:
    """构造 Linux 管理器，并固定 WSL 探测结果。"""
    executable = path if path is not None else str(tmp_path / 'dnplayer.exe')
    linux.check_wsl_environment = lambda: wsl
    return LinuxEmulatorManager(
        DeviceConfig(DEVICE_EMULATOR_TYPE=emulator_type, DEVICE_EMULATOR_PATH=executable),
        serial=serial,
    )


def test_wsl_flag_is_captured_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """构造时读取一次 WSL 探测结果。"""
    monkeypatch.setattr(linux, 'check_wsl_environment', lambda: True)
    manager = LinuxEmulatorManager(DeviceConfig(), serial=None)

    assert manager._is_wsl is True


# ── 进程状态 ────────────────────────────────────────────────────────────────


def test_check_running_prefers_online_adb_then_host_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """ADB 已上线直接算运行，否则按 WSL 的 tasklist 或原生 pgrep 判断。"""
    online = _manager(tmp_path)
    monkeypatch.setattr(online, '_read_online_adb_serials', lambda: ['emulator-5554'])
    assert online.check_emulator_running() is True

    wsl = _manager(tmp_path, wsl=True)
    monkeypatch.setattr(wsl, '_read_online_adb_serials', list)
    monkeypatch.setattr(wsl, '_check_windows_process_running', lambda: True)
    assert wsl.check_emulator_running() is True

    native = _manager(tmp_path)
    monkeypatch.setattr(native, '_read_online_adb_serials', list)
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        linux.subprocess,
        'run',
        lambda command, **_kwargs: recorded.append(command) or _FakeResult(),
    )
    assert native.check_emulator_running() is True
    assert recorded == [['pgrep', '-f', 'dnplayer.exe']]

    def raise_called_process(*_args: object, **_kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, 'pgrep')

    monkeypatch.setattr(linux.subprocess, 'run', raise_called_process)
    assert native.check_emulator_running() is False

    native._process_name = None
    assert native.check_emulator_running() is False


# ── 启动 ────────────────────────────────────────────────────────────────────


def test_start_emulator_spawns_configured_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """启动命令按 shell 规则拆分后交给 Popen，并等待上线。"""
    manager = _manager(tmp_path, path='/opt/emu/run --mode fast')
    calls: list[list[str]] = []
    monkeypatch.setattr(
        linux.subprocess,
        'Popen',
        lambda command, **_kwargs: calls.append(command) or object(),
    )
    waits: list[None] = []
    monkeypatch.setattr(manager, 'wait_for_emulator_online', lambda: waits.append(None))

    manager.start_emulator()

    assert calls == [['/opt/emu/run', '--mode', 'fast']]
    assert waits == [None]


def test_start_emulator_requires_path_and_wraps_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """缺宿主路径时拒绝启动，等待上线的 DeviceError 透传，其余异常包装。"""
    broken = _manager(tmp_path, path='')
    broken._path = None
    with pytest.raises(DeviceNotFoundError, match='未设置模拟器路径（WSL 需要显式设置）'):
        broken.start_emulator()

    manager = _manager(tmp_path)
    monkeypatch.setattr(linux.subprocess, 'Popen', lambda *_args, **_kwargs: object())

    def raise_online() -> None:
        raise DeviceError('模拟器启动超时')

    monkeypatch.setattr(manager, 'wait_for_emulator_online', raise_online)
    with pytest.raises(DeviceError, match='模拟器启动超时'):
        manager.start_emulator()

    def raise_popen(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('boom')

    monkeypatch.setattr(linux.subprocess, 'Popen', raise_popen)
    with pytest.raises(DeviceError, match='启动模拟器失败: boom'):
        manager.start_emulator()


# ── 停止 ────────────────────────────────────────────────────────────────────


def test_stop_emulator_uses_wsl_taskkill_or_native_pkill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """WSL 用 taskkill.exe，原生 Linux 用 pkill -9。"""
    wsl = _manager(tmp_path, wsl=True)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_wsl_run(command: list[str], **kwargs: object) -> _FakeResult:
        calls.append((command, kwargs))
        return _FakeResult()

    monkeypatch.setattr(linux.subprocess, 'run', fake_wsl_run)
    wsl.stop_emulator()
    assert calls == [
        (
            ['taskkill.exe', '/f', '/im', 'dnplayer.exe'],
            {'capture_output': True, 'text': True, 'check': False},
        )
    ]

    monkeypatch.setattr(
        linux.subprocess,
        'run',
        lambda *_args, **_kwargs: _FakeResult(returncode=1, stderr='access denied'),
    )
    with pytest.raises(DeviceError, match='access denied'):
        wsl.stop_emulator()

    native = _manager(tmp_path)
    recorded: list[tuple[list[str], dict[str, object]]] = []

    def fake_native_run(command: list[str], **kwargs: object) -> _FakeResult:
        recorded.append((command, kwargs))
        return _FakeResult()

    monkeypatch.setattr(linux.subprocess, 'run', fake_native_run)
    native.stop_emulator()
    assert recorded == [(['pkill', '-9', '-f', 'dnplayer.exe'], {'check': True})]


def test_stop_emulator_requires_process_name_and_wraps_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """缺进程名时拒绝停止，宿主异常包装为 DeviceError。"""
    broken = _manager(tmp_path)
    broken._process_name = None
    with pytest.raises(DeviceError, match='未设置进程名，无法停止模拟器'):
        broken.stop_emulator()

    manager = _manager(tmp_path)

    def raise_run(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('denied')

    monkeypatch.setattr(linux.subprocess, 'run', raise_run)
    with pytest.raises(DeviceError, match='停止模拟器失败: denied'):
        manager.stop_emulator()


# ── ADB 状态与 WSL 进程检查 ─────────────────────────────────────────────────


def test_adb_serial_and_wsl_process_probes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """ADB 只保留 device 状态并对失败降级，WSL 进程检查按 tasklist 文本判断。"""
    manager = _manager(tmp_path)
    monkeypatch.setattr(
        linux.executor,
        'read_adb_devices',
        lambda: [('emulator-5554', 'device'), ('emulator-5556', 'offline')],
    )
    assert manager._read_online_adb_serials() == ['emulator-5554']

    def raise_device_error() -> list[tuple[str, str]]:
        raise DeviceError('adb missing')

    monkeypatch.setattr(linux.executor, 'read_adb_devices', raise_device_error)
    assert manager._read_online_adb_serials() == []

    wsl = _manager(tmp_path, wsl=True)
    wsl._process_name = None
    assert wsl._check_windows_process_running() is False

    wsl._process_name = 'dnplayer.exe'
    monkeypatch.setattr(
        linux.subprocess,
        'run',
        lambda *_args, **_kwargs: _FakeResult(stdout='INFO: No tasks are running'),
    )
    assert wsl._check_windows_process_running() is False

    monkeypatch.setattr(
        linux.subprocess,
        'run',
        lambda *_args, **_kwargs: _FakeResult(stdout='dnplayer.exe   1234'),
    )
    assert wsl._check_windows_process_running() is True
