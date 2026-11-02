"""静态验证 case：用外挂截图跑主页检查器。

样本属于临时验证数据，放在仓库之外，不随仓库提交。
运行方式::

    python tools/debug_toolkit/main.py e2e --static home_check
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autowsgr.application.controller import home
from autowsgr.application.navigation.types import PageName


DESC = '主页检查器静态验证: 主页 / 公告浮窗 / 奖励浮窗 / 确认浮窗'

# 外挂截图目录；换机器或换样本时只改这里。
_SHOT_DIR = Path('C:/ShiinaKuroko/01.Project/debug/nav/静态模板/首页')


def run(rt: Any) -> bool:
    """按场景切换外挂截图并校验四个识别入口。"""
    ctx = rt.ctx

    # 1. 主页模板：干净主页应当命中。
    rt.use_frame(_SHOT_DIR / '主页模板.png')
    home = rt.action('检查主页模板', home.check_home_page, ctx)
    if home is rt.FAILED:
        return False
    if not rt.check('主页模板命中', lambda: home):
        return False

    # 2. 公告浮窗：已勾选样本应当命中且勾选状态为真。
    rt.use_frame(_SHOT_DIR / '每日公告浮窗-勾选.png')
    checked = rt.action('识别公告浮窗（已勾选）', home.check_home_news_overlay, ctx)
    if checked is rt.FAILED:
        return False
    if not rt.check('公告浮窗命中且已勾选', lambda: checked.matched and checked.checked is True):
        return False

    # 3. 公告浮窗：未勾选样本应当命中且勾选状态为假。
    rt.use_frame(_SHOT_DIR / '每日公告浮窗-未勾选.png')
    unchecked = rt.action('识别公告浮窗（未勾选）', home.check_home_news_overlay, ctx)
    if unchecked is rt.FAILED:
        return False
    if not rt.check(
        '公告浮窗命中且未勾选',
        lambda: unchecked.matched and unchecked.checked is False,
    ):
        return False

    # 4. 每日奖励浮窗：两个样本都应当命中。
    for name in ('每日奖励浮窗1.png', '每日奖励浮窗2.png'):
        rt.use_frame(_SHOT_DIR / name)
        reward = rt.action(f'识别每日奖励浮窗（{name}）', home.check_home_reward_overlay, ctx)
        if reward is rt.FAILED:
            return False
        if not rt.check(f'每日奖励浮窗命中（{name}）', lambda: reward):
            return False

    # 5. 每日奖励确认浮窗：确认样本应当命中。
    rt.use_frame(_SHOT_DIR / '每日奖励确认浮窗.png')
    confirm = rt.action('识别每日奖励确认浮窗', home.check_home_reward_confirm, ctx)
    if confirm is rt.FAILED:
        return False
    return rt.check('每日奖励确认浮窗命中', lambda: confirm)
