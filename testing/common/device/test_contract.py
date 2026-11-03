"""验证 common/device 的重写契约：包出口、配置边界与对外流程。

直接调用方：设备接入流程的回归检查。

直接依赖：device 包、ADB 执行器、截图流程与平台层。

边界：不连接真实设备，不访问网络。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy
import pytest

from autowsgr.common import device
from autowsgr.common.device.adb_engine import executor
from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.foundation import delay, platform
from autowsgr.common.device.device_engine.orchestration import discovery, lifecycle, screenshot
from autowsgr.common.device.errors import DeviceConnectionError
from autowsgr.common.device.scrcpy_engine.executor import ScrcpyEngine


def _install_adb(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[subprocess.CompletedProcess],
) -> list[list[str]]:
    """把 ADB 命令替换成按顺序返回预设结果的替身，并记录每次参数。"""
    calls: list[list[str]] = []
    pending = iter(responses)

    def run(_executable: object, command: object, **_kwargs: object) -> subprocess.CompletedProcess:
        calls.append([str(item) for item in command])
        return next(pending)

    monkeypatch.setattr(executor, 'find_adb_executable', lambda _path=None: Path('adb.exe'))
    monkeypatch.setattr(executor, '_execute_adb_command', run)
    return calls


def test_public_entry_points_stay_on_their_own_namespaces() -> None:
    """根包只导出 service 命名空间，服务与串流引擎都从各自模块取用。"""
    assert device.__all__ == ['service']
    assert device.service.DeviceService
    assert not hasattr(device, 'DeviceService')

    service = device.service.DeviceService()

    assert service.resolution == (0, 0)
    assert not service.is_connected()

    engine = ScrcpyEngine()

    assert engine.resolution == (0, 0)
    assert not engine.is_scrcpy_connected()
    for entry in (
        'connect_scrcpy',
        'capture_screenshot',
        'disconnect_scrcpy',
        'click_screen',
        'swipe_screen',
        'long_press_screen',
        'send_key_event',
        'input_text',
        'reconnect_to_display',
    ):
        assert callable(getattr(engine, entry))


def test_device_config_owns_its_fields() -> None:
    """配置模型接受 device 自有字段并拒绝历史遗留字段。"""
    config = DeviceConfig(
        ADB_CONNECTION='127.0.0.1:16384',
        DEVICE_OPERATION_DELAY_MIN=0.1,
        DEVICE_OPERATION_DELAY_MAX=0.2,
    )

    assert config.ADB_CONNECTION == '127.0.0.1:16384'
    assert config.DEVICE_OPERATION_DELAY_MIN == 0.1
    with pytest.raises(ValueError, match='Extra inputs are not permitted'):
        DeviceConfig(DEVICE_OLD_OPTION=True)


def test_adb_engine_ships_bundled_resources() -> None:
    """ADB 可执行文件与依赖 DLL 随包发布，显式路径会被解析成绝对路径。"""
    bundled_adb = Path(executor.__file__).with_name('adb.exe')

    assert bundled_adb.is_file()
    assert (bundled_adb.parent / 'AdbWinApi.dll').is_file()
    assert (bundled_adb.parent / 'AdbWinUsbApi.dll').is_file()
    assert executor.find_adb_executable(bundled_adb) == bundled_adb.resolve()


def test_adb_device_listing_and_connect_confirm_device_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设备列表跳过标题行，连接必须以 get-state 返回 device 收尾。"""
    calls = _install_adb(
        monkeypatch,
        [
            subprocess.CompletedProcess(
                [],
                0,
                stdout='List of devices attached\nserial-a\tdevice\nserial-b\tunauthorized\n',
                stderr='',
            ),
            subprocess.CompletedProcess([], 0, stdout='connected', stderr=''),
            subprocess.CompletedProcess([], 0, stdout='device\n', stderr=''),
        ],
    )

    assert executor.read_adb_devices() == [
        ('serial-a', 'device'),
        ('serial-b', 'unauthorized'),
    ]

    executor.connect_adb_device('serial-a')

    assert calls == [
        ['devices'],
        ['connect', 'serial-a'],
        ['-s', 'serial-a', 'get-state'],
    ]


def test_screenshot_flows_from_png_bytes_to_saved_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADB 截图把 PNG 字节解码成 BGR 数组，保存流程再把帧与允许目录交给 system.files。"""
    source = numpy.zeros((2, 3, 3), dtype=numpy.uint8)
    source[:, :] = (0, 0, 255)
    success, encoded = cv2.imencode('.png', source)
    assert success
    _install_adb(
        monkeypatch,
        [
            subprocess.CompletedProcess([], 0, stdout='connected', stderr=''),
            subprocess.CompletedProcess([], 0, stdout='device\n', stderr=''),
            subprocess.CompletedProcess([], 0, stdout=encoded.tobytes(), stderr=b''),
        ],
    )

    screen = executor.capture_device_screenshot('serial-a')

    assert screen.shape == (2, 3, 3)
    assert tuple(screen[0, 0]) == (0, 0, 255)

    saved: dict[str, object] = {}

    class FakeSession:
        scrcpy = type('FakeScrcpy', (), {'capture_screenshot': staticmethod(lambda: screen)})()

    def record_save(image: numpy.ndarray, path: str, *, allowed_root: str) -> None:
        saved['image'] = image
        saved['path'] = path
        saved['allowed_root'] = allowed_root

    monkeypatch.setattr(screenshot.files, 'save_image', record_save)

    screenshot._save_device_screenshot(FakeSession(), 'capture.png', allowed_root='captures')

    assert saved['image'] is screen
    assert saved['path'] == 'capture.png'
    assert saved['allowed_root'] == 'captures'


def test_discovery_and_timing_follow_platform_contract() -> None:
    """设备发现、平台 serial 计算与操作延迟都走当前平台契约。"""
    config = DeviceConfig(ADB_CONNECTION='127.0.0.1:16384', DEVICE_EMULATOR_TYPE='MuMu')

    assert discovery.recognize_emulator_type('127.0.0.1:16384') is platform.EmulatorType.mumu
    assert discovery.recognize_emulator_type('unknown') is None
    assert discovery.resolve_device_serial(config) == '127.0.0.1:16384'
    assert (
        platform.calculate_default_emulator_serial(
            platform.EmulatorType.mumu,
            platform.OSType.windows,
        )
        == '127.0.0.1:16384'
    )

    manager = lifecycle.create_emulator_process_manager(
        DeviceConfig(DEVICE_EMULATOR_TYPE='云手机'),
        platform.OSType.windows,
    )
    assert manager.check_emulator_running()
    manager.start_emulator()
    manager.stop_emulator()

    delay.configure_operation_delay_bounds(0.2, 0.2)
    try:
        assert delay.calculate_operation_delay() == 0.2
    finally:
        delay.configure_operation_delay_bounds(0.0, 0.0)

    with pytest.raises(ValueError, match='0 <= minimum <= maximum'):
        delay.configure_operation_delay_bounds(0.2, 0.1)


def test_discovery_filters_offline_devices_and_rejects_empty_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候选发现只保留在线设备，没有候选时不能进入交互选择。"""
    monkeypatch.setattr(
        executor,
        'read_adb_devices',
        lambda _path=None: [
            ('unknown', 'device'),
            ('127.0.0.1:16384', 'device'),
            ('offline-device', 'offline'),
        ],
    )

    candidates = discovery.discover_emulator_candidates()

    assert [candidate.serial for candidate in candidates] == ['127.0.0.1:16384', 'unknown']
    with pytest.raises(DeviceConnectionError, match='没有可供选择'):
        discovery.select_emulator_candidate([])
