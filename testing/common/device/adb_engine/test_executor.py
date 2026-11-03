"""模块功能：验证 ADB 执行器的完整命令流程。

直接调用方：设备连接层与模拟器发现逻辑。

直接依赖：pytest、adb_engine.executor 与 subprocess 结果替身。

边界：所有命令都用替身执行，不启动真实 adb、不访问设备。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from autowsgr.common.device.adb_engine import executor
from autowsgr.common.device.errors import DeviceConnectionError, DeviceNotFoundError


def _completed(
    *, returncode: int = 0, stdout: str | bytes = '', stderr: str | bytes = ''
) -> subprocess.CompletedProcess:
    """构造一条 ADB 命令结果。"""
    return subprocess.CompletedProcess(
        args=['adb'], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _install_commands(
    monkeypatch: pytest.MonkeyPatch,
    results: list[subprocess.CompletedProcess],
) -> list[tuple[tuple[str, ...], bool, float]]:
    """接管命令执行与可执行文件查找，按顺序返回预置结果。"""
    calls: list[tuple[tuple[str, ...], bool, float]] = []
    pending = list(results)

    def fake_execute(
        _adb_path: Path,
        arguments: list[str],
        *,
        binary: bool = False,
        timeout: float = 10.0,
    ) -> subprocess.CompletedProcess:
        calls.append((tuple(arguments), binary, timeout))
        return pending.pop(0)

    monkeypatch.setattr(executor, 'find_adb_executable', lambda _adb_path=None: Path('adb.exe'))
    monkeypatch.setattr(executor, '_execute_adb_command', fake_execute)
    return calls


def test_find_executable_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式路径必须存在，宿主 PATH 没有 adb 时回落到随包资源。"""
    with pytest.raises(DeviceNotFoundError, match='找不到指定的 ADB'):
        executor.find_adb_executable(tmp_path / 'adb.exe')

    adb_path = tmp_path / 'adb.exe'
    adb_path.write_bytes(b'')
    assert executor.find_adb_executable(adb_path) == adb_path.resolve()

    assert executor._BUNDLED_ADB_PATH.is_file()
    monkeypatch.setattr(executor.sys, 'platform', 'win32')
    monkeypatch.setattr(executor.shutil, 'which', lambda _name: None)
    assert executor.find_adb_executable() == executor._BUNDLED_ADB_PATH


def test_read_devices_parses_and_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """设备列表跳过标题与空行，命令失败和超时都转成连接错误。"""
    real_execute = executor._execute_adb_command
    calls = _install_commands(
        monkeypatch,
        [
            _completed(
                stdout=(
                    'List of devices attached\n'
                    '\n'
                    'emulator-5554\tdevice\n'
                    '127.0.0.1:16384\tdevice\n'
                    '127.0.0.1:5555\toffline\n'
                ),
            ),
        ],
    )

    assert executor.read_adb_devices() == [
        ('emulator-5554', 'device'),
        ('127.0.0.1:16384', 'device'),
        ('127.0.0.1:5555', 'offline'),
    ]
    assert calls[0][0] == ('devices',)

    _install_commands(
        monkeypatch,
        [_completed(returncode=1, stderr='adb server is out of date')],
    )
    with pytest.raises(
        DeviceConnectionError, match='读取 ADB 设备列表失败: adb server is out of date'
    ):
        executor.read_adb_devices()

    monkeypatch.setattr(executor, 'find_adb_executable', lambda _adb_path=None: Path('adb.exe'))
    monkeypatch.setattr(executor, '_execute_adb_command', real_execute)

    def raise_timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd='adb', timeout=10.0)

    monkeypatch.setattr(executor.subprocess, 'run', raise_timeout)
    with pytest.raises(DeviceConnectionError, match='ADB 命令超时: devices'):
        executor.read_adb_devices()


def test_connect_pipeline_confirms_device_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """连接流程先 connect 再按 serial 查状态，异常状态与传输失败都报错。"""
    calls = _install_commands(monkeypatch, [_completed(), _completed(stdout='device\n')])

    executor.connect_adb_device('emulator-5554')

    assert calls[0][0] == ('connect', 'emulator-5554')
    assert calls[1][0] == ('-s', 'emulator-5554', 'get-state')

    _install_commands(monkeypatch, [_completed(), _completed(stdout='offline\n')])
    with pytest.raises(DeviceConnectionError, match='设备未就绪: offline'):
        executor.connect_adb_device('emulator-5554')

    _install_commands(monkeypatch, [_completed(returncode=1, stderr='failed to connect')])
    with pytest.raises(DeviceConnectionError, match='连接设备失败: failed to connect'):
        executor.connect_adb_device('127.0.0.1:16384')


def test_capture_screenshot_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """screencap 输出 PNG 时解码为 BGR，非法或空输出转成连接错误。"""
    image = np.array(
        [[[10, 20, 30], [40, 50, 60]], [[70, 80, 90], [100, 110, 120]]], dtype=np.uint8
    )
    ok, encoded = cv2.imencode('.png', image)
    assert ok
    calls = _install_commands(monkeypatch, [_completed(stdout=encoded.tobytes())])
    monkeypatch.setattr(executor, 'connect_adb_device', lambda *_args, **_kwargs: None)

    frame = executor.capture_device_screenshot('emulator-5554')

    assert np.array_equal(frame, image)
    assert calls[0][0] == ('-s', 'emulator-5554', 'exec-out', 'screencap', '-p')
    assert calls[0][1] is True

    _install_commands(monkeypatch, [_completed(stdout=b'not-a-png')])
    with pytest.raises(DeviceConnectionError, match='不是有效 PNG'):
        executor.capture_device_screenshot('emulator-5554')

    _install_commands(monkeypatch, [_completed(stdout=b'')])
    with pytest.raises(DeviceConnectionError, match='ADB 截图失败'):
        executor.capture_device_screenshot('emulator-5554')


def test_restart_adb_server_kills_then_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """重启 server 先杀进程、等待、再启动，启动失败时带上错误输出。"""
    calls = _install_commands(
        monkeypatch,
        [_completed(), _completed(returncode=1, stderr='cannot bind')],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(executor.time, 'sleep', sleeps.append)

    with pytest.raises(DeviceConnectionError, match='启动 ADB server 失败: cannot bind'):
        executor.restart_adb_server()

    assert [arguments for arguments, _binary, _timeout in calls] == [
        ('kill-server',),
        ('start-server',),
    ]
    assert sleeps == [1.0]
