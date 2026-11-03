"""模块功能：验证 Scrcpy 执行器的连接、截图、输入与控制通道流程。

直接调用方：设备会话与设备服务。

直接依赖：pytest、scrcpy_engine.executor、struct 与 socket/设备替身。

边界：不启动真实 scrcpy 服务、不连接真实设备、不读取视频流。
"""

from __future__ import annotations

import struct
import sys
from types import SimpleNamespace

import pytest

from autowsgr.common.device.device_engine.foundation.delay import configure_operation_delay_bounds
from autowsgr.common.device.errors import DeviceConnectionError
from autowsgr.common.device.scrcpy_engine import executor


class _FakeSocket:
    """记录发送内容并按预置脚本抛错的 socket 替身。"""

    def __init__(self, *, recv: bytes = b'\x00', failures: int = 0) -> None:
        self.recv_bytes = recv
        self.failures = failures
        self.sent: list[bytes] = []
        self.closed = False
        self.options: list[tuple[int, int, int]] = []

    def sendall(self, data: bytes) -> None:
        """记录发送内容，按脚本在前几次抛连接错误。"""
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError('控制通道已断开')
        self.sent.append(data)

    def recv(self, _size: int) -> bytes:
        """返回预置首字节。"""
        return self.recv_bytes

    def setsockopt(self, level: int, option: int, value: int) -> None:
        """记录 socket 选项。"""
        self.options.append((level, option, value))

    def close(self) -> None:
        """记录关闭动作。"""
        self.closed = True


class _FakeDevice:
    """记录 adb 设备操作的替身。"""

    def __init__(
        self,
        *,
        connection: object = None,
        connection_failures: int = 0,
        window_size: tuple[int, int] | None = (960, 540),
    ) -> None:
        self.connection = connection
        self.connection_failures = connection_failures
        self.window_size_value = window_size
        self.calls: list[tuple[object, ...]] = []

    def window_size(self) -> tuple[int, int] | None:
        """返回设备窗口尺寸。"""
        return self.window_size_value

    def push(self, local: str, remote: str) -> None:
        """记录服务端推送。"""
        self.calls.append(('push', local, remote))

    def shell(self, command: object, *, stream: bool = False) -> object:
        """记录启动命令并返回流替身。"""
        self.calls.append(('shell', command, stream))
        return SimpleNamespace(closed=False, close=lambda: None)

    def create_connection(self, _network: object, _name: str) -> object:
        """按预置次数失败后返回视频或控制 socket。"""
        if self.connection_failures > 0:
            self.connection_failures -= 1
            raise OSError('connection refused')
        return self.connection


def _engine(**overrides: object) -> executor.ScrcpyEngine:
    """构造执行器并可直接覆盖内部状态。"""
    engine = executor.ScrcpyEngine()
    for name, value in overrides.items():
        setattr(engine, name, value)
    return engine


def _messages(engine: executor.ScrcpyEngine, monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """拦截控制消息发送并收集原始字节。"""
    messages: list[bytes] = []
    monkeypatch.setattr(engine, '_send_control_message', messages.append)
    return messages


def _stub_connect_steps(engine: executor.ScrcpyEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """把连接流程的五个阶段换成空实现。"""
    for name in (
        '_push_scrcpy_server',
        '_start_scrcpy_server',
        '_connect_video_channel',
        '_connect_control_channel',
        '_start_frame_decoder',
    ):
        monkeypatch.setattr(engine, name, lambda: None)


@pytest.fixture(autouse=True)
def _reset_delay_bounds() -> None:
    """用例结束后恢复全局操作延迟范围。"""
    yield
    configure_operation_delay_bounds(0.0, 0.0)


# ── 连接与断开流程 ──────────────────────────────────────────────────────────


def test_connect_flow_opens_channels_returns_resolution_then_disconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连接按服务、双通道、解码、首帧顺序执行；断开后清空设备、分辨率与最近帧。"""
    device = _FakeDevice(window_size=(1080, 1920))
    engine = _engine(_frame_ready=SimpleNamespace(wait=lambda timeout: timeout >= 0))
    steps: list[str] = []
    for name in (
        '_push_scrcpy_server',
        '_start_scrcpy_server',
        '_connect_video_channel',
        '_connect_control_channel',
        '_start_frame_decoder',
    ):
        monkeypatch.setattr(engine, name, lambda _name=name: steps.append(_name))

    assert engine.connect_scrcpy(device, 'emulator-5554') == (1080, 1920)
    assert steps == [
        '_push_scrcpy_server',
        '_start_scrcpy_server',
        '_connect_video_channel',
        '_connect_control_channel',
        '_start_frame_decoder',
    ]
    assert engine._device is device
    assert engine._serial == 'emulator-5554'

    engine._frame_ready = SimpleNamespace(clear=lambda: None)
    engine.disconnect_scrcpy()
    assert engine.is_scrcpy_connected() is False
    assert engine.resolution == (0, 0)
    assert engine._last_frame is None

    fallback = _engine(_frame_ready=SimpleNamespace(wait=lambda timeout: timeout >= 0))
    _stub_connect_steps(fallback, monkeypatch)

    assert (
        fallback.connect_scrcpy(_FakeDevice(window_size=None), 'emulator-5554')
        == executor._DEFAULT_SCREEN_RESOLUTION
    )


def test_connect_flow_cleans_up_when_first_frame_never_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首帧等待超时后关闭通道、清空设备并抛出连接错误。"""
    device = _FakeDevice()
    engine = _engine(
        _frame_ready=SimpleNamespace(wait=lambda timeout: timeout < 0),
        _screenshot_timeout=5.0,
    )
    closed: list[bool] = []
    _stub_connect_steps(engine, monkeypatch)
    monkeypatch.setattr(engine, '_close_scrcpy_channels', lambda: closed.append(True))

    with pytest.raises(DeviceConnectionError, match=r'未能在 5\.0s 内产生首帧'):
        engine.connect_scrcpy(device, 'emulator-5554')
    assert closed == [True]
    assert engine._device is None


def test_server_preparation_requires_jar_then_pushes_and_starts_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """缺少 jar 时明确报错；就位后推到固定路径，并用版本、视频参数与显示器编号启动。"""
    missing = tmp_path / 'missing.jar'  # type: ignore[operator]
    monkeypatch.setattr(executor, '_SCRCPY_SERVER_FILE', missing)
    with pytest.raises(DeviceConnectionError, match=r'找不到 scrcpy-server\.jar'):
        executor.ScrcpyEngine()._push_scrcpy_server()

    jar = tmp_path / 'scrcpy-server.jar'  # type: ignore[operator]
    jar.write_bytes(b'jar')
    device = _FakeDevice()
    engine = _engine(_device=device, _display_id=2)
    sleeps: list[float] = []
    monkeypatch.setattr(executor, '_SCRCPY_SERVER_FILE', jar)
    monkeypatch.setattr(executor.time, 'sleep', sleeps.append)

    engine._push_scrcpy_server()
    engine._start_scrcpy_server()

    assert device.calls[0] == ('push', str(jar), executor._DEVICE_JAR_PATH)
    _kind, command, stream = device.calls[1]
    assert stream is True
    assert command[0] == f'CLASSPATH={executor._DEVICE_JAR_PATH}'
    assert command[4] == executor._SCRCPY_SERVER_VERSION
    assert 'video=true' in command
    assert 'audio=false' in command
    assert 'display_id=2' in command
    assert sleeps == [executor._SCRCPY_SERVER_START_DELAY_SECONDS]


def test_channel_handshakes_require_dummy_byte_and_retry_until_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """视频通道必须收到首字节；连接失败按上限重试，控制通道建立后关闭 Nagle。"""
    monkeypatch.setitem(
        sys.modules,
        'adbutils',
        SimpleNamespace(Network=SimpleNamespace(LOCAL_ABSTRACT='localabstract')),
    )

    empty = _engine(_device=_FakeDevice(connection=_FakeSocket(recv=b'')))
    with pytest.raises(DeviceConnectionError, match='未收到 scrcpy dummy byte'):
        empty._connect_video_channel()

    failing = _engine(
        _device=_FakeDevice(connection_failures=executor._SCRCPY_CHANNEL_CONNECT_ATTEMPTS)
    )
    monkeypatch.setattr(executor.time, 'sleep', lambda _seconds: None)
    with pytest.raises(DeviceConnectionError, match='无法连接 scrcpy-server 视频通道'):
        failing._connect_video_channel()

    control = _FakeSocket()
    engine = _engine(_device=_FakeDevice(connection=control))
    engine._connect_control_channel()
    assert engine._control_socket is control
    assert control.options == [(executor.socket.IPPROTO_TCP, executor.socket.TCP_NODELAY, 1)]


# ── 截图流程 ────────────────────────────────────────────────────────────────


def test_screenshot_flow_returns_frame_recovers_dead_stream_and_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有帧直接返回；流失效时先恢复通道；恢复后仍无帧则按超时长度报错。"""
    frame = object()
    ready = _engine(_alive=True, _last_frame=frame)
    assert ready.capture_screenshot() is frame

    dead = _engine(_alive=False, _last_frame=None)
    ensured: list[bool] = []

    def _ensure() -> None:
        ensured.append(True)
        dead._alive = True
        dead._last_frame = frame

    monkeypatch.setattr(dead, '_ensure_scrcpy_stream', _ensure)
    assert dead.capture_screenshot() is frame
    assert ensured == [True]

    stuck = _engine(_alive=True, _last_frame=None, _screenshot_timeout=10.0)
    monkeypatch.setattr(stuck, '_ensure_scrcpy_stream', lambda: None)
    monkeypatch.setattr(executor.time, 'monotonic', iter([0.0, 100.0]).__next__)
    monkeypatch.setattr(executor.time, 'sleep', lambda _seconds: None)
    with pytest.raises(DeviceConnectionError, match=r'截图超时 \(10.0s\)'):
        stuck.capture_screenshot()


# ── 输入流程 ────────────────────────────────────────────────────────────────


def test_input_events_encode_press_move_and_key_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """点击换算像素后发送按下与抬起并等待延迟，滑动均分移动事件、长按在按下与抬起间等待、按键先按下再抬起。"""
    engine = _engine(_resolution=(960, 540))
    messages = _messages(engine, monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr(executor.time, 'sleep', sleeps.append)

    engine.click_screen(0.5, 0.25)

    assert [struct.unpack('>BBqIIHHHII', message) for message in messages] == [
        (
            executor._TYPE_INJECT_TOUCH_EVENT,
            executor._ACTION_DOWN,
            executor._POINTER_ID_FINGER,
            480,
            135,
            960,
            540,
            65535,
            0,
            0,
        ),
        (
            executor._TYPE_INJECT_TOUCH_EVENT,
            executor._ACTION_UP,
            executor._POINTER_ID_FINGER,
            480,
            135,
            960,
            540,
            0,
            0,
            0,
        ),
    ]
    assert sleeps == [executor._GESTURE_EVENT_INTERVAL_SECONDS]

    sleeps.clear()
    monkeypatch.setattr(executor, 'calculate_operation_delay', lambda: 0.25)
    engine.click_screen(0.5, 0.25, delay=True)
    assert sleeps == [0.25, executor._GESTURE_EVENT_INTERVAL_SECONDS]

    gesture = executor.ScrcpyEngine()
    events: list[tuple[object, ...]] = []
    sleeps.clear()
    monkeypatch.setattr(gesture, '_send_touch_event', lambda *args, **_kwargs: events.append(args))
    monkeypatch.setattr(executor.time, 'sleep', sleeps.append)

    gesture.swipe_screen(0.0, 0.0, 1.0, 1.0, duration=0.032)
    assert events == [
        (executor._ACTION_DOWN, 0.0, 0.0),
        (executor._ACTION_MOVE, 0.5, 0.5),
        (executor._ACTION_MOVE, 1.0, 1.0),
        (executor._ACTION_UP, 1.0, 1.0),
    ]

    events.clear()
    sleeps.clear()
    gesture.long_press_screen(0.2, 0.3, duration=2.0)
    assert events == [
        (executor._ACTION_DOWN, 0.2, 0.3),
        (executor._ACTION_UP, 0.2, 0.3),
    ]
    assert sleeps == [2.0]

    key_engine = executor.ScrcpyEngine()
    messages = _messages(key_engine, monkeypatch)
    monkeypatch.setattr(executor.time, 'sleep', lambda _seconds: None)
    key_engine.send_key_event(4)
    assert [struct.unpack('>BBIII', message) for message in messages] == [
        (executor._TYPE_INJECT_KEYCODE, executor._KEY_ACTION_DOWN, 4, 0, 0),
        (executor._TYPE_INJECT_KEYCODE, executor._KEY_ACTION_UP, 4, 0, 0),
    ]


def test_text_flow_routes_ascii_injection_and_unicode_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ASCII 走注入并按 300 字节截断；多字节文本走剪贴板，超长再按协议上限截断。"""
    engine = executor.ScrcpyEngine()
    messages = _messages(engine, monkeypatch)

    engine.input_text('a' * 400)
    engine.input_text('中文')

    injected = messages[0]
    assert struct.unpack('>BI', injected[:5]) == (executor._TYPE_INJECT_TEXT, 300)
    assert injected[5:] == b'a' * 300

    clipboard = messages[1]
    assert struct.unpack('>BQBI', clipboard[:14]) == (
        executor._TYPE_SET_CLIPBOARD,
        0,
        1,
        len('中文'.encode()),
    )
    assert clipboard[14:] == '中文'.encode()

    engine.input_text('中' * 300000)
    assert struct.unpack('>BQBI', messages[2][:14])[3] == (
        executor._CLIPBOARD_TEXT_MAX_LENGTH_BYTES
    )


# ── 通道与重连流程 ──────────────────────────────────────────────────────────


def test_stream_recovery_switches_display_and_retries_control_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目标显示器未变且流存活时不重建通道；控制消息首次写入失败时恢复通道后重发，重发仍失败抛原始错误。"""
    engine = _engine(_alive=True, _display_id=2)
    reconnects: list[bool] = []
    monkeypatch.setattr(engine, '_reconnect_scrcpy_stream', lambda: reconnects.append(True))

    engine.reconnect_to_display(2)
    engine.reconnect_to_display(3)

    assert reconnects == [True]
    assert engine._display_id == 3

    engine = executor.ScrcpyEngine()
    first = _FakeSocket(failures=1)
    second = _FakeSocket()
    sockets = [first, second]
    ensured: list[bool] = []
    monkeypatch.setattr(engine, '_require_control_channel', lambda: sockets.pop(0))
    monkeypatch.setattr(engine, '_ensure_scrcpy_stream', lambda: ensured.append(True))

    engine._send_control_message(b'payload')
    assert first.sent == []
    assert second.sent == [b'payload']
    assert ensured == [True]

    broken = _FakeSocket(failures=2)
    monkeypatch.setattr(engine, '_require_control_channel', lambda: broken)
    with pytest.raises(ConnectionError, match='控制通道已断开'):
        engine._send_control_message(b'payload')
