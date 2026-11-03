"""模块功能：验证模拟器识别的完整发现流程。

直接调用方：设备连接层。

直接依赖：pytest、orchestration.discovery 与 ADB 设备列表替身。

边界：不执行真实 adb 命令、不连接模拟器。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType
from autowsgr.common.device.device_engine.orchestration import discovery
from autowsgr.common.device.errors import DeviceConnectionError


@pytest.mark.parametrize(
    ('serial', 'expected'),
    [
        ('emulator-5554', EmulatorType.leidian),
        ('127.0.0.1:16384', EmulatorType.mumu),
        ('127.0.0.1:16499', EmulatorType.mumu),
        ('127.0.0.1:17000', EmulatorType.mumu),
        ('127.0.0.1:62001', EmulatorType.mumu),
        ('127.0.0.1:5555', EmulatorType.bluestacks),
        ('127.0.0.1:5560', EmulatorType.bluestacks),
        ('127.0.0.1:5599', EmulatorType.bluestacks),
        ('127.0.0.1:5600', EmulatorType.bluestacks),
        ('127.0.0.1:1234', None),
        ('192.168.1.5:5555', None),
        ('emulator-5554-extra', None),
    ],
)
def test_recognize_emulator_type_by_serial(serial: str, expected: EmulatorType | None) -> None:
    """按 serial 规则识别模拟器类型，未知格式返回 None。"""
    assert discovery.recognize_emulator_type(serial) is expected


def test_discover_candidates_and_known_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    """候选发现只保留在线设备并排序，已知 serial 的自动连接失败不影响后续探测。"""
    monkeypatch.setattr(
        discovery.executor,
        'read_adb_devices',
        lambda _adb_path=None: [
            ('127.0.0.1:16384', 'device'),
            ('emulator-5554', 'offline'),
            ('emulator-5554', 'device'),
            ('127.0.0.1:5555', 'device'),
        ],
    )

    candidates = discovery.discover_emulator_candidates()

    assert [candidate.serial for candidate in candidates] == [
        '127.0.0.1:16384',
        '127.0.0.1:5555',
        'emulator-5554',
    ]
    assert [candidate.emulator_type for candidate in candidates] == [
        EmulatorType.mumu,
        EmulatorType.bluestacks,
        EmulatorType.leidian,
    ]
    description = candidates[0].description

    assert '127.0.0.1:16384' in description
    assert 'MuMu' in description
    assert '(device)' in description
    assert '未知' in discovery.EmulatorCandidate('192.168.1.5:5555', None, 'offline').description

    attempted: list[str] = []

    def connect(serial: str, _adb_path: object = None) -> None:
        attempted.append(serial)
        if serial == '127.0.0.1:62001':
            raise DeviceConnectionError('连接被拒绝')

    monkeypatch.setattr(discovery.executor, 'find_adb_executable', lambda: Path('adb.exe'))
    monkeypatch.setattr(discovery.executor, 'connect_adb_device', connect)
    monkeypatch.setattr(
        discovery.executor,
        'read_adb_devices',
        lambda _adb_path=None: [('127.0.0.1:16384', 'device')],
    )

    assert discovery.discover_known_adb_devices() == [('127.0.0.1:16384', 'device')]
    assert attempted == ['127.0.0.1:16384', '127.0.0.1:62001']


def test_select_emulator_candidate_interaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """交互选择拒绝空候选与非终端，支持编号选择、重试与取消。"""
    candidates = [
        discovery.EmulatorCandidate('emulator-5554', EmulatorType.leidian, 'device'),
        discovery.EmulatorCandidate('127.0.0.1:16384', EmulatorType.mumu, 'device'),
    ]

    with pytest.raises(DeviceConnectionError, match='没有可供选择的在线设备'):
        discovery.select_emulator_candidate([])

    monkeypatch.setattr(discovery.sys, 'stdin', io.StringIO())
    with pytest.raises(DeviceConnectionError, match='请设置 ADB_CONNECTION'):
        discovery.select_emulator_candidate(candidates)

    monkeypatch.setattr(discovery.sys, 'stdin', _tty_stdin())
    answers = iter(['9', 'x', '1'])
    monkeypatch.setattr('builtins.input', lambda _prompt='': next(answers))

    assert discovery.select_emulator_candidate(candidates) == '127.0.0.1:16384'

    def raise_eof(_prompt: str = '') -> str:
        raise EOFError

    monkeypatch.setattr('builtins.input', raise_eof)

    with pytest.raises(DeviceConnectionError, match='用户取消了设备选择'):
        discovery.select_emulator_candidate(candidates)


def test_resolve_device_serial_follows_configuration_before_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式配置优先，其次单候选直接返回，多候选按类型过滤后再交互选择。"""
    monkeypatch.setattr(
        discovery,
        'discover_emulator_candidates',
        lambda _adb_path=None: pytest.fail('不应触发自动发现'),
    )

    assert (
        discovery.resolve_device_serial(DeviceConfig(ADB_CONNECTION='emulator-5554'))
        == 'emulator-5554'
    )

    monkeypatch.setattr(discovery, 'discover_emulator_candidates', lambda _adb_path=None: [])

    with pytest.raises(DeviceConnectionError, match='未检测到任何在线 Android 设备'):
        discovery.resolve_device_serial(DeviceConfig())

    single = [discovery.EmulatorCandidate('emulator-5554', EmulatorType.leidian, 'device')]
    monkeypatch.setattr(discovery, 'discover_emulator_candidates', lambda _adb_path=None: single)

    assert discovery.resolve_device_serial(DeviceConfig()) == 'emulator-5554'

    leidian = discovery.EmulatorCandidate('emulator-5554', EmulatorType.leidian, 'device')
    mumu = discovery.EmulatorCandidate('127.0.0.1:16384', EmulatorType.mumu, 'device')
    mumu_extra = discovery.EmulatorCandidate('127.0.0.1:17000', EmulatorType.mumu, 'device')
    monkeypatch.setattr(
        discovery,
        'discover_emulator_candidates',
        lambda _adb_path=None: [leidian, mumu, mumu_extra],
    )

    seen: list[list[discovery.EmulatorCandidate]] = []
    monkeypatch.setattr(
        discovery,
        'select_emulator_candidate',
        lambda candidates: seen.append(list(candidates)) or '127.0.0.1:17000',
    )

    assert (
        discovery.resolve_device_serial(DeviceConfig(DEVICE_EMULATOR_TYPE=EmulatorType.mumu))
        == '127.0.0.1:17000'
    )
    assert seen == [[mumu, mumu_extra]]

    seen.clear()
    monkeypatch.setattr(
        discovery,
        'select_emulator_candidate',
        lambda candidates: seen.append(list(candidates)) or 'emulator-5554',
    )

    missing = DeviceConfig(DEVICE_EMULATOR_TYPE=EmulatorType.bluestacks)

    assert discovery.resolve_device_serial(missing) == 'emulator-5554'
    assert seen == [[leidian, mumu, mumu_extra]]


def _tty_stdin() -> io.StringIO:
    """返回伪装成交互终端的输入流。"""

    class _TtyStdin(io.StringIO):
        def isatty(self) -> bool:
            return True

    return _TtyStdin()
