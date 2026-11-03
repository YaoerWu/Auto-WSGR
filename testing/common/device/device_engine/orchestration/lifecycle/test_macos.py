"""模块功能：验证 macOS 宿主模拟器管理器的状态探测、启停与 MuMu 实例控制流程。

用替身替换 subprocess 与 mumutool，不启动真实模拟器或宿主命令。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType
from autowsgr.common.device.device_engine.orchestration.lifecycle import macos
from autowsgr.common.device.device_engine.orchestration.lifecycle.macos import MacEmulatorManager
from autowsgr.common.device.errors import DeviceError, DeviceNotFoundError


class _FakeProcess:
    """记录 Popen 返回值的最小替身。"""

    def __init__(self, stdout: bytes = b'', stderr: bytes = b'') -> None:
        self._stdout = stdout
        self._stderr = stderr

    def communicate(self) -> tuple[bytes, bytes]:
        """返回预设的输出流。"""
        return self._stdout, self._stderr


def _manager(
    emulator_type: EmulatorType = EmulatorType.mumu,
    *,
    path: str | None = '/Applications/MuMuPlayer.app',
    serial: str | None = '127.0.0.1:16384',
) -> MacEmulatorManager:
    """构造指向固定应用路径的管理器。"""
    return MacEmulatorManager(
        DeviceConfig(DEVICE_EMULATOR_TYPE=emulator_type, DEVICE_EMULATOR_PATH=path),
        serial=serial,
    )


def _patch_popen(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """替换 subprocess.Popen，记录每次命令行。"""
    calls: list[list[str]] = []

    def fake_popen(command: list[str], **_kwargs: object) -> _FakeProcess:
        calls.append(command)
        return _FakeProcess()

    monkeypatch.setattr(macos.subprocess, 'Popen', fake_popen)
    return calls


def _patch_wait(monkeypatch: pytest.MonkeyPatch, manager: MacEmulatorManager) -> list[None]:
    """替换等待上线，避免真实轮询。"""
    waits: list[None] = []
    monkeypatch.setattr(manager, 'wait_for_emulator_online', lambda: waits.append(None))
    return waits


# ── 进程状态 ────────────────────────────────────────────────────────────────


def test_check_running_matches_process_and_mumu_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 MuMu 只看进程，MuMu 还要求 ADB 端口命中某个实例。"""
    bluestacks = _manager(EmulatorType.bluestacks)
    monkeypatch.setattr(macos.subprocess, 'check_output', lambda *_args: b'1234')
    assert bluestacks.check_emulator_running() is True
    bluestacks._process_name = None
    assert bluestacks.check_emulator_running() is False

    def raise_called_process(*_args: object, **_kwargs: object) -> bytes:
        raise subprocess.CalledProcessError(1, 'pgrep')

    monkeypatch.setattr(macos.subprocess, 'check_output', raise_called_process)
    assert bluestacks.check_emulator_running() is False

    mumu = _manager(serial='127.0.0.1:16416')
    monkeypatch.setattr(macos.subprocess, 'check_output', lambda *_args: b'1234')
    instances = {'return': {'results': [{'adb_port': '16384'}, {'adb_port': '16416'}]}}
    monkeypatch.setattr(mumu, '_read_mumu_instance_info', lambda: instances)
    assert mumu.check_emulator_running() is True

    monkeypatch.setattr(
        mumu, '_read_mumu_instance_info', lambda: {'return': {'results': [{'adb_port': '16384'}]}}
    )
    assert mumu.check_emulator_running() is False


# ── 启动 ────────────────────────────────────────────────────────────────────


def test_start_emulator_opens_app_and_restarts_mumu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两类模拟器都用 open -a 启动，MuMu 额外重启端口匹配的实例。"""
    bluestacks = _manager(EmulatorType.bluestacks)
    calls = _patch_popen(monkeypatch)
    waits = _patch_wait(monkeypatch, bluestacks)
    bluestacks.start_emulator()
    assert calls == [['open', '-a', '/Applications/MuMuPlayer.app']]
    assert waits == [None]

    mumu = _manager(serial='127.0.0.1:16416')
    mumu_calls = _patch_popen(monkeypatch)
    mumu_waits = _patch_wait(monkeypatch, mumu)
    restarted: list[None] = []
    monkeypatch.setattr(mumu, '_restart_mumu_instance', lambda: restarted.append(None))
    mumu.start_emulator()
    assert mumu_calls == [['open', '-a', '/Applications/MuMuPlayer.app']]
    assert restarted == [None]
    assert mumu_waits == [None]


def test_start_emulator_requires_path_and_wraps_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺应用路径时拒绝启动，宿主异常包装为 DeviceError。"""
    broken = _manager(path=None)
    with pytest.raises(DeviceNotFoundError, match='未设置模拟器路径，无法启动'):
        broken.start_emulator()

    manager = _manager(EmulatorType.bluestacks)

    def raise_popen(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('boom')

    monkeypatch.setattr(macos.subprocess, 'Popen', raise_popen)
    with pytest.raises(DeviceError, match='启动模拟器失败: boom'):
        manager.start_emulator()


# ── 停止 ────────────────────────────────────────────────────────────────────


def test_stop_emulator_pkills_non_mumu_and_skips_mumu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MuMu 不支持命令行停止，其余模拟器用 pkill 结束进程。"""
    mumu = _manager()
    calls = _patch_popen(monkeypatch)
    mumu.stop_emulator()
    assert calls == []

    bluestacks = _manager(EmulatorType.bluestacks)
    pkill_calls = _patch_popen(monkeypatch)
    bluestacks.stop_emulator()
    assert pkill_calls == [['pkill', '-9', '-f', 'MuMuPlayer.app']]


def test_stop_emulator_requires_process_name_and_wraps_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺进程名时拒绝停止，宿主异常包装为 DeviceError。"""
    broken = _manager(EmulatorType.bluestacks, path=None)
    with pytest.raises(DeviceError, match='未设置进程名，无法停止'):
        broken.stop_emulator()

    manager = _manager(EmulatorType.bluestacks)

    def raise_popen(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('denied')

    monkeypatch.setattr(macos.subprocess, 'Popen', raise_popen)
    with pytest.raises(DeviceError, match='停止模拟器失败: denied'):
        manager.stop_emulator()


# ── MuMu 实例信息 ───────────────────────────────────────────────────────────


def test_mumu_instance_info_reads_tool_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """工具路径基于应用包，文件缺失或输出不可解析时降级为空字典。"""
    assert _manager(path=None)._mumu_tool_path == ''
    assert _manager()._mumu_tool_path.endswith('Contents/MacOS/mumutool')

    manager = _manager()
    monkeypatch.setattr(macos.os.path, 'isfile', lambda _path: False)
    assert manager._read_mumu_instance_info() == {}

    monkeypatch.setattr(macos.os.path, 'isfile', lambda _path: True)
    payload = {'return': {'results': [{'adb_port': '16384'}]}}
    monkeypatch.setattr(
        macos.subprocess,
        'Popen',
        lambda *_args, **_kwargs: _FakeProcess(stdout=json.dumps(payload).encode()),
    )
    assert manager._read_mumu_instance_info() == payload

    for raw in (b'not-json', b'\xff'):
        monkeypatch.setattr(
            macos.subprocess, 'Popen', lambda *_args, _raw=raw, **_kwargs: _FakeProcess(stdout=_raw)
        )
        assert manager._read_mumu_instance_info() == {}


def test_restart_mumu_instance_uses_matched_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """按 ADB 端口找到实例下标后提交 restart，找不到时不下发命令。"""
    manager = _manager(serial='127.0.0.1:16416')
    calls = _patch_popen(monkeypatch)
    monkeypatch.setattr(
        manager,
        '_read_mumu_instance_info',
        lambda: {'return': {'results': [{'adb_port': '16384'}, {'adb_port': '16416'}]}},
    )
    manager._restart_mumu_instance()
    assert calls == [[manager._mumu_tool_path, 'restart', '1']]

    monkeypatch.setattr(
        manager,
        '_read_mumu_instance_info',
        lambda: {'return': {'results': [{'adb_port': '16384'}]}},
    )
    manager._restart_mumu_instance()
    assert calls == [[manager._mumu_tool_path, 'restart', '1']]
