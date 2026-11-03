"""模块功能：验证屏幕输入转发、应用启停与显示器查找。

直接调用方：设备服务。
直接依赖：pytest、orchestration.operation 与 scrcpy/adb 替身。
边界：不执行真实设备操作。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.common.device.device_engine.orchestration import operation
from autowsgr.common.device.errors import DeviceConnectionError


class _FakeScrcpy:
    """记录屏幕输入调用的串流引擎替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def click_screen(self, *args: object, **kwargs: object) -> None:
        """记录点击调用。"""
        self.calls.append(('click_screen', args, kwargs))

    def swipe_screen(self, *args: object, **kwargs: object) -> None:
        """记录滑动调用。"""
        self.calls.append(('swipe_screen', args, kwargs))

    def long_press_screen(self, *args: object, **kwargs: object) -> None:
        """记录长按调用。"""
        self.calls.append(('long_press_screen', args, kwargs))

    def send_key_event(self, *args: object, **kwargs: object) -> None:
        """记录按键调用。"""
        self.calls.append(('send_key_event', args, kwargs))

    def input_text(self, *args: object, **kwargs: object) -> None:
        """记录文本输入调用。"""
        self.calls.append(('input_text', args, kwargs))


class _FakeAdb:
    """返回预置 shell 输出并记录应用操作的 adb 替身。"""

    def __init__(self, shell_output: object = '') -> None:
        self.shell_output = shell_output
        self.calls: list[object] = []

    def shell(self, command: str) -> object:
        """记录并返回预置输出。"""
        self.calls.append(command)
        return self.shell_output

    def app_start(self, package: str) -> None:
        """记录启动动作。"""
        self.calls.append(('app_start', package))

    def app_stop(self, package: str) -> None:
        """记录停止动作。"""
        self.calls.append(('app_stop', package))


def _session(adb_device: object = None) -> SimpleNamespace:
    """构造只带串流引擎和可选 adb 句柄的会话替身。"""
    session = SimpleNamespace(scrcpy=_FakeScrcpy(), adb_device=adb_device)

    def require() -> object:
        if session.adb_device is None:
            raise DeviceConnectionError('设备未连接，请先调用 device.service.connect()')
        return session.adb_device

    session._require_adb_device = require
    return session


def test_screen_inputs_forward_arguments() -> None:
    """点击、滑动、长按、按键与文本输入带各自参数原样转发。"""
    session = _session()

    operation._click_screen(session, 0.5, 0.25, delay=True)
    operation._swipe_screen(session, 0.1, 0.2, 0.3, 0.4, duration=0.8, delay=True)
    operation._long_press_screen(session, 0.5, 0.5, duration=2.0)
    operation._send_key_event(session, 4, delay=True)
    operation._input_text(session, 'hello', delay=True)

    assert session.scrcpy.calls == [
        ('click_screen', (0.5, 0.25), {'delay': True}),
        ('swipe_screen', (0.1, 0.2, 0.3, 0.4, 0.8), {'delay': True}),
        ('long_press_screen', (0.5, 0.5, 2.0), {}),
        ('send_key_event', (4,), {'delay': True}),
        ('input_text', ('hello',), {'delay': True}),
    ]


def test_application_commands_use_adb_and_require_connection() -> None:
    """应用启停走 adb 句柄；未连接设备时应用操作直接报错。"""
    adb = _FakeAdb()
    session = _session(adb)

    operation._start_application(session, 'com.game')
    operation._stop_application(session, 'com.game')

    assert adb.calls == [('app_start', 'com.game'), ('app_stop', 'com.game')]

    with pytest.raises(DeviceConnectionError, match='设备未连接'):
        operation._start_application(_session(), 'com.game')


def test_application_inspection_reads_adb_output() -> None:
    """运行状态与所属显示器都从 adb 输出判定，非文本输出转成字符串。"""
    adb = _FakeAdb('u0_a123 1234 1 com.other\nu0_a124 5678 1 com.game')
    session = _session(adb)

    assert operation._check_application_running(session, 'com.game') is True
    assert operation._check_application_running(session, 'com.absent') is False
    assert adb.calls == ['ps -A', 'ps -A']

    dump = (
        'Display #0 (activities):\n'
        '  topResumedActivity=ActivityRecord{1 u0 com.other/.Main}\n'
        'Display #2 (activities):\n'
        '  topResumedActivity=ActivityRecord{2 u0 com.game/.Main}\n'
    )
    assert operation._find_application_display(_session(_FakeAdb(dump)), 'com.game') == 2

    other = 'Display #1 (activities):\n  topResumedActivity=ActivityRecord{1 u0 com.other/.Main}\n'
    assert operation._find_application_display(_session(_FakeAdb(other)), 'com.game') is None

    orphan = '  topResumedActivity=ActivityRecord{1 u0 com.game/.Main}\n'
    assert operation._find_application_display(_session(_FakeAdb(orphan)), 'com.game') is None

    assert operation._execute_shell_command(_session(_FakeAdb(123)), 'echo') == '123'
