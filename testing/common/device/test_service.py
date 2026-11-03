"""模块功能：验证设备服务对连接、平台输入、截图与模拟器入口的编排。

直接调用方：runtime 控制器与业务流程。
直接依赖：pytest、device.service 与各编排模块替身。
边界：不连接真实设备、不访问真实模拟器。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from autowsgr.common.device import service
from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.device.device_engine.orchestration.connection import DeviceInfo


if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeScrcpy:
    """记录显示器跟随动作的串流引擎替身。"""

    def __init__(self) -> None:
        self.displays: list[int] = []
        self._resolution = (960, 540)

    @property
    def resolution(self) -> tuple[int, int]:
        """返回预置分辨率。"""
        return self._resolution

    def reconnect_to_display(self, display_id: int) -> None:
        """记录切换显示器。"""
        self.displays.append(display_id)


@pytest.fixture
def device_service(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, list[tuple[str, tuple[object, ...]]]]:
    """构造替换了会话与各编排入口的设备服务。"""
    calls: list[tuple[str, tuple[object, ...]]] = []

    def record(name: str) -> Callable[..., object]:
        def entry(*args: object, **kwargs: object) -> object:
            calls.append((name, (*args, kwargs)))
            return f'{name}-result'

        return entry

    for module_name, module in (
        ('connection', service.connection),
        ('operation', service.operation),
        ('screenshot', service.screenshot),
        ('lifecycle', service.lifecycle.service),
    ):
        for attribute in dir(module):
            if attribute.startswith('_') and callable(getattr(module, attribute)):
                monkeypatch.setattr(module, attribute, record(f'{module_name}.{attribute}'))

    instance = service.DeviceService(DeviceConfig())
    instance._session = SimpleNamespace(scrcpy=_FakeScrcpy(), config=DeviceConfig(), serial=None)
    return instance, calls


def test_connect_returns_info_and_follows_only_with_package(
    device_service: tuple[object, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连接返回设备信息；只有给了包名才立刻跟随该应用的显示器。"""
    instance, _calls = device_service
    monkeypatch.setattr(
        service.connection,
        '_connect_device',
        lambda _session: DeviceInfo(serial='emulator-5554', resolution=(960, 540)),
    )
    followed: list[str] = []
    monkeypatch.setattr(instance, 'follow_display', followed.append)

    info = instance.connect()

    assert info == DeviceInfo(serial='emulator-5554', resolution=(960, 540))
    assert followed == []
    assert instance._session.scrcpy.displays == []

    instance.connect(package='com.game')

    assert followed == ['com.game']


def test_follow_display_polls_until_found_or_timeout(
    device_service: tuple[object, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """应用出现在某块显示器上时切换一次；超时仍找不到则不切换也不再等待。"""
    instance, _calls = device_service
    answers = iter([None, 2])
    sleeps: list[float] = []
    monkeypatch.setattr(
        service.operation, '_find_application_display', lambda _session, _package: next(answers)
    )
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)

    instance.follow_display('com.game')

    assert instance._session.scrcpy.displays == [2]
    assert sleeps == [service._APPLICATION_DISPLAY_POLL_SECONDS]

    monkeypatch.setattr(
        service.operation, '_find_application_display', lambda _session, _package: None
    )
    monkeypatch.setattr(service.time, 'monotonic', iter([0.0, 100.0]).__next__)
    sleeps.clear()

    instance.follow_display('com.game')

    assert instance._session.scrcpy.displays == [2]
    assert sleeps == []


def test_screen_and_application_entries_delegate(
    device_service: tuple[object, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输入类入口与应用启停检查入口把参数原样转给操作编排。"""
    instance, calls = device_service
    followed: list[str] = []
    monkeypatch.setattr(instance, 'follow_display', followed.append)

    instance.click(0.5, 0.25, delay=True)
    instance.swipe(0.1, 0.2, 0.3, 0.4, 0.8, delay=True)
    instance.long_tap(0.5, 0.5, 2.0)
    instance.key_event(4, delay=True)
    instance.text('hello', delay=True)

    assert calls == [
        ('operation._click_screen', (instance._session, 0.5, 0.25, {'delay': True})),
        (
            'operation._swipe_screen',
            (instance._session, 0.1, 0.2, 0.3, 0.4, 0.8, {'delay': True}),
        ),
        ('operation._long_press_screen', (instance._session, 0.5, 0.5, 2.0, {})),
        ('operation._send_key_event', (instance._session, 4, {'delay': True})),
        ('operation._input_text', (instance._session, 'hello', {'delay': True})),
    ]

    calls.clear()
    instance.start_app('com.game')
    instance.stop_app('com.game')
    instance.check_app_running('com.game')
    instance.shell('ps -A')

    assert followed == ['com.game']
    assert [call[0] for call in calls] == [
        'operation._start_application',
        'operation._stop_application',
        'operation._check_application_running',
        'operation._execute_shell_command',
    ]


def test_screenshot_and_lifecycle_entries_delegate(
    device_service: tuple[object, list[tuple[object, ...]]],
) -> None:
    """截图与连接、模拟器维护入口全部委托给对应编排层。"""
    instance, calls = device_service

    assert instance.screenshot() == 'screenshot._capture_device_screenshot-result'
    instance.save_screenshot('shot.png', allowed_root='C:/tmp')

    assert instance.resolution == (960, 540)
    assert calls == [
        ('screenshot._capture_device_screenshot', (instance._session, {})),
        (
            'screenshot._save_device_screenshot',
            (instance._session, 'shot.png', {'allowed_root': 'C:/tmp'}),
        ),
    ]

    calls.clear()
    assert instance.is_connected() == 'connection._is_device_connected-result'
    instance.disconnect()
    instance.reconnect()
    instance.check_emulator_running()
    instance.start_emulator()
    instance.stop_emulator()
    instance.restart_emulator()
    instance.wait_emulator_online(30)

    assert [call[0] for call in calls] == [
        'connection._is_device_connected',
        'connection._disconnect_device',
        'connection._reconnect_device',
        'lifecycle._check_emulator_running',
        'lifecycle._start_emulator',
        'lifecycle._stop_emulator',
        'lifecycle._restart_emulator',
        'lifecycle._wait_for_emulator_online',
    ]
    assert calls[-1][1][1] == 30
