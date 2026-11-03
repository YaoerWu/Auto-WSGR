"""模块功能：验证 Windows 宿主模拟器管理器的状态探测、启停与命令行拼装流程。

按宿主类型组织用例：同一个流程内覆盖状态探测、启动、停止和控制台命令拼装，
用替身替换 subprocess 与宿主命令执行，不启动真实模拟器进程。
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType
from autowsgr.common.device.device_engine.orchestration.lifecycle import windows
from autowsgr.common.device.device_engine.orchestration.lifecycle.windows import (
    WindowsEmulatorManager,
)
from autowsgr.common.device.errors import DeviceError, DeviceNotFoundError


if TYPE_CHECKING:
    import pathlib


class _FakeProcess:
    """记录 Popen 返回值的最小替身。"""

    def __init__(self, stdout: bytes = b'', stderr: bytes = b'') -> None:
        self._stdout = stdout
        self._stderr = stderr

    def communicate(self) -> tuple[bytes, bytes]:
        """返回预设的输出流。"""
        return self._stdout, self._stderr


def _manager(
    tmp_path: pathlib.Path,
    emulator_type: EmulatorType = EmulatorType.leidian,
    *,
    serial: str | None = 'emulator-5554',
) -> WindowsEmulatorManager:
    """构造指向临时目录宿主程序的管理器。"""
    path = tmp_path / 'dnplayer.exe'
    path.write_text('', encoding='utf-8')
    return WindowsEmulatorManager(
        DeviceConfig(DEVICE_EMULATOR_TYPE=emulator_type, DEVICE_EMULATOR_PATH=str(path)),
        serial=serial,
    )


def _patch_console(
    monkeypatch: pytest.MonkeyPatch,
    manager: WindowsEmulatorManager,
    attribute: str,
    outputs: list[str],
) -> list[str]:
    """替换模拟器控制台命令，按顺序返回输出并记录命令名。"""
    commands: list[str] = []
    queue = iter(outputs)

    def fake(command: str, _command_arg: str = '') -> str:
        commands.append(command)
        return next(queue, '')

    monkeypatch.setattr(manager, attribute, fake)
    return commands


def _patch_wait(monkeypatch: pytest.MonkeyPatch, manager: WindowsEmulatorManager) -> list[None]:
    """替换等待上线，避免真实轮询。"""
    waits: list[None] = []
    monkeypatch.setattr(manager, 'wait_for_emulator_online', lambda: waits.append(None))
    return waits


# ── 进程状态 ────────────────────────────────────────────────────────────────


def test_check_running_reads_host_specific_signals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """雷电看 running 文本，MuMu 看 JSON 字段，云手机始终在线且不跑宿主命令。"""
    leidian = _manager(tmp_path)
    leidian_commands = _patch_console(
        monkeypatch, leidian, '_execute_ldconsole_command', ['running\n', 'stopped']
    )
    assert leidian.check_emulator_running() is True
    assert leidian.check_emulator_running() is False
    assert leidian_commands == ['isrunning', 'isrunning']

    mumu = _manager(tmp_path, EmulatorType.mumu)
    mumu_commands = _patch_console(
        monkeypatch,
        mumu,
        '_execute_mumu_manager_command',
        [json.dumps({'is_android_started': True}), 'not-json', json.dumps({})],
    )
    assert mumu.check_emulator_running() is True
    assert mumu.check_emulator_running() is False
    assert mumu.check_emulator_running() is False
    assert mumu_commands == ['is_android_started'] * 3

    yunshouji = _manager(tmp_path, EmulatorType.yunshouji)
    host_calls: list[list[str]] = []
    monkeypatch.setattr(yunshouji, '_execute_host_command', host_calls.append)
    assert yunshouji.check_emulator_running() is True
    assert host_calls == []


def test_check_running_others_scans_tasklist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """其余模拟器按 tasklist 是否出现 PID 判断，执行失败或缺进程名都算未运行。"""
    manager = _manager(tmp_path, EmulatorType.others)
    outputs = [b'info PID 1234', b'no tasks']
    commands: list[list[str]] = []

    def fake_check_output(command: list[str], **_kwargs: object) -> bytes:
        commands.append(command)
        return outputs.pop(0)

    monkeypatch.setattr(windows.subprocess, 'check_output', fake_check_output)
    assert manager.check_emulator_running() is True
    assert manager.check_emulator_running() is False
    assert commands == [
        ['tasklist', '/fi', 'ImageName eq dnplayer.exe'],
        ['tasklist', '/fi', 'ImageName eq dnplayer.exe'],
    ]

    def raise_called_process(*_args: object, **_kwargs: object) -> bytes:
        raise subprocess.CalledProcessError(1, 'tasklist')

    monkeypatch.setattr(windows.subprocess, 'check_output', raise_called_process)
    assert manager.check_emulator_running() is False

    manager._process_name = None
    assert manager.check_emulator_running() is False


# ── 启动 ────────────────────────────────────────────────────────────────────


def test_start_emulator_launches_host_then_waits_online(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """三类宿主各用宿主命令启动并等待上线；云手机跳过，缺路径与宿主异常都有明确错误。"""
    leidian = _manager(tmp_path)
    leidian_commands = _patch_console(monkeypatch, leidian, '_execute_ldconsole_command', [''])
    leidian_waits = _patch_wait(monkeypatch, leidian)
    leidian.start_emulator()
    assert leidian_commands == ['launch']
    assert leidian_waits == [None]

    mumu = _manager(tmp_path, EmulatorType.mumu)
    mumu_commands = _patch_console(monkeypatch, mumu, '_execute_mumu_manager_command', [''])
    mumu_waits = _patch_wait(monkeypatch, mumu)
    mumu.start_emulator()
    assert mumu_commands == ['launch']
    assert mumu_waits == [None]

    others = _manager(tmp_path, EmulatorType.others)
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(
        windows.subprocess, 'Popen', lambda command, **_kwargs: popen_calls.append(command)
    )
    others_waits = _patch_wait(monkeypatch, others)
    others.start_emulator()
    assert popen_calls == [[others._path]]
    assert others_waits == [None]

    yunshouji = _manager(tmp_path, EmulatorType.yunshouji)
    skipped_popen: list[list[str]] = []
    monkeypatch.setattr(
        windows.subprocess, 'Popen', lambda command, **_kwargs: skipped_popen.append(command)
    )
    yunshouji_waits = _patch_wait(monkeypatch, yunshouji)
    yunshouji.start_emulator()
    assert skipped_popen == []
    assert yunshouji_waits == []

    broken = _manager(tmp_path)
    broken._path = None
    with pytest.raises(DeviceNotFoundError, match='未设置模拟器路径，无法启动'):
        broken.start_emulator()

    failing = _manager(tmp_path, EmulatorType.others)

    def raise_popen(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('boom')

    monkeypatch.setattr(windows.subprocess, 'Popen', raise_popen)
    with pytest.raises(DeviceError, match='启动模拟器失败: boom'):
        failing.start_emulator()


# ── 停止 ────────────────────────────────────────────────────────────────────


def test_stop_emulator_uses_host_command_by_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """雷电 quit、MuMu shutdown、其余 taskkill，云手机跳过；缺进程名与宿主异常都有明确错误。"""
    leidian = _manager(tmp_path)
    leidian_commands = _patch_console(monkeypatch, leidian, '_execute_ldconsole_command', [''])
    leidian.stop_emulator()
    assert leidian_commands == ['quit']

    mumu = _manager(tmp_path, EmulatorType.mumu)
    mumu_commands = _patch_console(monkeypatch, mumu, '_execute_mumu_manager_command', [''])
    mumu.stop_emulator()
    assert mumu_commands == ['shutdown']

    others = _manager(tmp_path, EmulatorType.others)
    run_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> object:
        run_calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(windows.subprocess, 'run', fake_run)
    others.stop_emulator()
    assert run_calls == [
        (['taskkill', '-f', '-im', 'dnplayer.exe'], {'check': True, 'capture_output': True})
    ]

    yunshouji = _manager(tmp_path, EmulatorType.yunshouji)
    yunshouji_commands = _patch_console(monkeypatch, yunshouji, '_execute_ldconsole_command', [''])
    yunshouji.stop_emulator()
    assert yunshouji_commands == []

    unnamed = _manager(tmp_path, EmulatorType.others)
    unnamed._process_name = None
    with pytest.raises(DeviceError, match='未设置进程名，无法停止模拟器'):
        unnamed.stop_emulator()

    broken = _manager(tmp_path, EmulatorType.others)

    def raise_run(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError('denied')

    monkeypatch.setattr(windows.subprocess, 'run', raise_run)
    with pytest.raises(DeviceError, match='停止模拟器失败: denied'):
        broken.stop_emulator()


# ── 控制台命令行 ────────────────────────────────────────────────────────────


def test_ldconsole_command_maps_serial_to_instance_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """ADB serial 换算为 ldconsole 实例下标，附件参数追加到末尾，缺失路径或控制台都报错。"""
    (tmp_path / 'ldconsole.exe').write_text('', encoding='utf-8')
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        WindowsEmulatorManager,
        '_execute_host_command',
        staticmethod(lambda command: recorded.append(command) or 'out'),
    )

    for serial, index in (
        ('emulator-5554', '0'),
        ('emulator-5556', '1'),
        ('emulator-5560', '3'),
        (None, '0'),
    ):
        manager = _manager(tmp_path, serial=serial)
        assert manager._execute_ldconsole_command('isrunning') == 'out'
        assert recorded[-1] == [str(tmp_path / 'ldconsole.exe'), 'isrunning', '--index', index]

    manager = _manager(tmp_path)
    manager._execute_ldconsole_command('launch', 'extra')
    assert recorded[-1][-1] == 'extra'

    manager._path = None
    with pytest.raises(DeviceNotFoundError, match='未设置雷电模拟器路径'):
        manager._execute_ldconsole_command('isrunning')

    (tmp_path / 'ldconsole.exe').unlink()
    broken = _manager(tmp_path)
    with pytest.raises(DeviceNotFoundError, match=r'找不到 ldconsole\.exe'):
        broken._execute_ldconsole_command('isrunning')


def test_mumu_manager_command_maps_port_to_instance_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """ADB 端口换算为 MuMuManager 实例下标，状态查询走 info、控制走 control，缺件报错。"""
    (tmp_path / 'MuMuManager.exe').write_text('', encoding='utf-8')
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        WindowsEmulatorManager,
        '_execute_host_command',
        staticmethod(lambda command: recorded.append(command) or ''),
    )

    for serial, index in (
        ('127.0.0.1:16384', '0'),
        ('127.0.0.1:16416', '1'),
        ('127.0.0.1:5555', '0'),
        (None, '0'),
    ):
        manager = _manager(tmp_path, EmulatorType.mumu, serial=serial)
        manager._execute_mumu_manager_command('is_android_started')
        assert recorded[-1] == [
            str(tmp_path / 'MuMuManager.exe'),
            'info',
            '-v',
            index,
            'is_android_started',
        ]

    manager = _manager(tmp_path, EmulatorType.mumu)
    manager._execute_mumu_manager_command('launch', 'arg')
    assert recorded[-1][1] == 'control'
    assert recorded[-1][-1] == 'arg'

    manager._path = None
    with pytest.raises(DeviceNotFoundError, match='未设置 MuMu 模拟器路径'):
        manager._execute_mumu_manager_command('is_android_started')

    (tmp_path / 'MuMuManager.exe').unlink()
    broken = _manager(tmp_path, EmulatorType.mumu)
    with pytest.raises(DeviceNotFoundError, match=r'找不到 MuMuManager\.exe'):
        broken._execute_mumu_manager_command('is_android_started')


def test_host_command_decodes_stdout_then_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """有标准输出时用它，空时退回错误流，非法 UTF-8 用替换字符。"""
    monkeypatch.setattr(
        windows.subprocess,
        'Popen',
        lambda *_args, **_kwargs: _FakeProcess(stdout=b'hello', stderr=b'ignored'),
    )
    assert WindowsEmulatorManager._execute_host_command(['tool']) == 'hello'

    monkeypatch.setattr(
        windows.subprocess,
        'Popen',
        lambda *_args, **_kwargs: _FakeProcess(stdout=b'', stderr=b'error'),
    )
    assert WindowsEmulatorManager._execute_host_command(['tool']) == 'error'

    monkeypatch.setattr(
        windows.subprocess,
        'Popen',
        lambda *_args, **_kwargs: _FakeProcess(stdout=b'\xff'),
    )
    assert WindowsEmulatorManager._execute_host_command(['tool']) == '\ufffd'
