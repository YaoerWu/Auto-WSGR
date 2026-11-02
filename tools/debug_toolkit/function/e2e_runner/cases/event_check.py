"""静态验证 case：用外挂截图跑普通推图 checker。

截图属于临时验证数据，放在仓库之外的 debug 目录，不随仓库提交。
运行方式::

    python tools/debug_toolkit/main.py e2e --static event_check
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autowsgr.application.controller.event import stage_push
from autowsgr.application.controller.event.stage_push import EventMode


DESC = '推图活动 checker 静态验证: 首页入口 / 地图难度 / 出征准备'

# 外挂截图目录；换机器或换活动时只改这里。
_SHOT_DIR = Path('C:/ShiinaKuroko/01.Project/debug/nav/静态模板/推图活动')


def run(rt: Any) -> bool:
    """按场景切换外挂截图并校验三个识别入口。"""
    ctx = rt.ctx

    # 1. 首页活动入口：有入口的首页应当命中。
    rt.use_frame(_SHOT_DIR / '活动首页.png')
    entry = rt.action(
        '检查首页活动入口', stage_push.check_event_entry, ctx, event_type='stage_push'
    )
    if entry is rt.FAILED:
        return False
    if not rt.check('首页活动入口命中', lambda: entry):
        return False

    # 2. 干净地图页：按钮显示困难说明当前是普通地图。
    rt.use_frame(_SHOT_DIR / '普通地图.png')
    normal_state = rt.action(
        '读取普通地图状态',
        stage_push.read_event_map_state,
        ctx,
        event_type='stage_push',
    )
    if normal_state is rt.FAILED:
        return False
    if not rt.check(
        '普通地图结论为普通难度',
        lambda: normal_state.current_mode is EventMode.NORMAL,
    ):
        return False

    # 3. 干净地图页：按钮显示普通说明当前是困难地图。
    rt.use_frame(_SHOT_DIR / '困难地图.png')
    hard_state = rt.action(
        '读取困难地图状态',
        stage_push.read_event_map_state,
        ctx,
        event_type='stage_push',
    )
    if hard_state is rt.FAILED:
        return False
    if not rt.check(
        '困难地图结论为困难难度',
        lambda: hard_state.current_mode is EventMode.HARD,
    ):
        return False

    # 4. 节点浮窗：目标章节 EX7 的准备前置页应当成立。
    rt.use_frame(_SHOT_DIR / 'E7出征前.png')
    prepare = rt.action(
        '检查出征准备前置页',
        stage_push.check_event_sortie_prepare,
        ctx,
        event_type='stage_push',
        stage='EX7',
    )
    if prepare is rt.FAILED:
        return False
    return rt.check('EX7 准备前置页成立', lambda: prepare)
