"""模块功能：验证任务页领奖与返回的单击契约。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.mission.page 与共用离屏上下文。

边界：用替身常量与设备控制记录点击，不加载模板、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.mission import page as mission_page
from autowsgr.application.controller.mission.page import MissionPage


if TYPE_CHECKING:
    import pytest


def test_clicks_claim_reward_and_back(
    monkeypatch: pytest.MonkeyPatch,
    ctx: Any,
    control: Any,
) -> None:
    """三个动作各自点击常量表里的落点。"""
    monkeypatch.setattr(
        mission_page,
        'constants',
        SimpleNamespace(
            CLICK_CLAIM_ALL=(0.11, 0.12),
            CLICK_REWARD_CONFIRM=(0.21, 0.22),
            CLICK_BACK=(0.31, 0.32),
        ),
    )

    page = MissionPage(ctx)
    page.click_claim_all()
    page.click_reward_confirm()
    page.go_back()

    assert control.clicks == [(0.11, 0.12), (0.21, 0.22), (0.31, 0.32)]
