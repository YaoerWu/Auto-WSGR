"""活动章节点击 E2E — 导航器活动链路的实机验证。

验证链路: 首页 → 活动地图 → 逐章节点开浮窗并校验指向 → 关闭浮窗 → 切换难度 → 再逐章节。
困难模式章节 EX7-EX12 (H1-H6), 普通模式章节 EX1-EX6 (E1-E6)。
难度切换由 UI 控制器执行, 落点来自 checker 读出的模式按钮中心, 不经过导航器。

用法::

    python tools/debug_toolkit/main.py e2e --event-type stage_push event_stage
"""

from __future__ import annotations

import time
from typing import Any


DESC = '活动章节点击: 首页 → 活动 → H1-H6 → 切普通 → E1-E6'

_EVENT_TYPE = 'stage_push'
_HARD_STAGES = ('EX7', 'EX8', 'EX9', 'EX10', 'EX11', 'EX12')
_NORMAL_STAGES = ('EX1', 'EX2', 'EX3', 'EX4', 'EX5', 'EX6')
_DIFFICULTY_SETTLE_SECONDS = 2.0


def run(rt: Any) -> bool:
    """执行活动链路并逐章节校验浮窗指向。"""
    from autowsgr.application.navigation.service import NavigationService
    from autowsgr.application.navigation.types import PageName

    ctx = rt.ctx
    navigator = NavigationService(ctx)

    # ① 起点: 回到首页
    if rt.action('回到首页', navigator.navigate_to, PageName.HOME) is rt.FAILED:
        return False

    # ② 首页 → 活动地图
    if rt.action('首页 → 活动地图', navigator.navigate_to, PageName.EVENT_MAP) is rt.FAILED:
        return False

    # ③ 困难模式逐章节点开
    if not _switch_difficulty(rt, ctx, 'hard'):
        return False
    for stage in _HARD_STAGES:
        if not _click_stage(rt, ctx, navigator, stage):
            return False

    # ④ 切回普通模式后逐章节点开
    if not _switch_difficulty(rt, ctx, 'normal'):
        return False
    for stage in _NORMAL_STAGES:
        if not _click_stage(rt, ctx, navigator, stage):
            return False

    return rt.state.failed == 0


def _switch_difficulty(rt: Any, ctx: Any, mode: str) -> bool:
    """切到目标难度; 已经在目标难度时跳过。"""
    from autowsgr.application.controller.event import stage_push
    from autowsgr.application.ui.controller.home.event_page import EventPage

    target = stage_push.EventMode(mode)
    state = stage_push.read_event_map_state(ctx, event_type=_EVENT_TYPE)
    if state.current_mode is target:
        rt.note(f'已在 {mode} 难度, 跳过切换')
        return True

    center = stage_push.read_mode_button_center(ctx, event_type=_EVENT_TYPE)
    if center is None:
        rt.check(f'切换难度 → {mode}: 读不到模式按钮中心', lambda: False)
        return False

    if (
        rt.action(
            f'切换难度 → {mode}',
            EventPage(ctx, event_type=_EVENT_TYPE).switch_difficulty,
            center,
        )
        is rt.FAILED
    ):
        return False
    time.sleep(_DIFFICULTY_SETTLE_SECONDS)

    after = stage_push.read_event_map_state(ctx, event_type=_EVENT_TYPE)
    rt.check(f'切换后难度 = {mode}', lambda: after.current_mode is target)
    return after.current_mode is target


def _click_stage(rt: Any, ctx: Any, navigator: Any, stage: str) -> bool:
    """点一个章节入口、校验浮窗指向, 再关掉浮窗回地图。"""
    from autowsgr.application.controller.event import stage_push
    from autowsgr.application.navigation.types import PageName

    if (
        rt.action(
            f'点击 {stage}',
            navigator.navigate_to,
            PageName.EVENT_STAGE_OVERLAY,
            stage=stage,
        )
        is rt.FAILED
    ):
        return False

    rt.check(
        f'{stage} 浮窗指向目标章节',
        lambda: stage_push.check_event_sortie_prepare(
            ctx,
            event_type=_EVENT_TYPE,
            stage=stage,
        ),
    )

    if rt.action(f'关闭 {stage} 浮窗', navigator.navigate_back) is rt.FAILED:
        return False
    return True
