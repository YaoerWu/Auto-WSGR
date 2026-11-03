"""模块功能：提供控制器测试共用的离屏上下文与点击记录。

直接调用方：testing/application/controller 下各模块测试。

直接依赖：types（SimpleNamespace 组装）与 pytest。

边界：只搭替身，不连设备、不读模板文件。
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest


class FakeControl:
    """记录点击、滑动与文字输入的设备控制替身。"""

    def __init__(self) -> None:
        """初始化为空的操作记录。"""
        self.clicks: list[tuple[float, float]] = []
        self.swipes: list[tuple[float, ...]] = []
        self.texts: list[str] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:
        """记录一次点击。"""
        del delay
        self.clicks.append((x, y))

    def swipe(self, *args: float) -> None:
        """记录一次滑动。"""
        self.swipes.append(args)

    def text(self, content: str) -> None:
        """记录一次文字输入。"""
        self.texts.append(content)


@pytest.fixture(autouse=True)
def _silence_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """控制器里的等待一律跳过，测试不真的睡。"""
    monkeypatch.setattr(time, 'sleep', lambda _seconds: None)


@pytest.fixture
def control() -> FakeControl:
    """返回一个空的设备控制替身。"""
    return FakeControl()


@pytest.fixture
def ctx(control: FakeControl) -> Any:
    """返回只暴露设备服务、断点与截图回写的离屏上下文。"""
    return SimpleNamespace(
        runtime=SimpleNamespace(ctrl=control),
        check_interrupt=lambda: None,
        record_screenshot=lambda _frame: None,
    )
