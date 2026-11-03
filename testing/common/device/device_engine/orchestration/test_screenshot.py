"""模块功能：验证截图读取与受限路径保存的委托关系。

直接调用方：设备服务。

直接依赖：pytest、orchestration.screenshot 与系统文件写入替身。

边界：不访问真实设备、不写真实文件。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from autowsgr.common.device.device_engine.orchestration import screenshot


if TYPE_CHECKING:
    import pytest


class _FakeScrcpy:
    """返回固定截图的串流引擎替身。"""

    def __init__(self, frame: object) -> None:
        self.frame = frame

    def capture_screenshot(self) -> object:
        """返回预置截图。"""
        return self.frame


def test_capture_returns_scrcpy_frame() -> None:
    """截图直接取串流引擎当前帧。"""
    frame = object()
    session = SimpleNamespace(scrcpy=_FakeScrcpy(frame))

    assert screenshot._capture_device_screenshot(session) is frame


def test_save_forwards_frame_and_allowed_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """保存截图时把当前帧、目标路径与允许根目录一起交给文件层。"""
    frame = object()
    session = SimpleNamespace(scrcpy=_FakeScrcpy(frame))
    calls: list[tuple[object, object, object]] = []

    def save_image(image: object, path: object, *, allowed_root: object) -> None:
        calls.append((image, path, allowed_root))

    monkeypatch.setattr(screenshot.files, 'save_image', save_image)

    screenshot._save_device_screenshot(session, 'shot.png', allowed_root=tmp_path)

    assert calls == [(frame, 'shot.png', tmp_path)]
