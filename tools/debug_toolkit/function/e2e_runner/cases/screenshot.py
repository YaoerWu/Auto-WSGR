"""链路自检 case: 连接设备、处理主页浮窗并识别主页。

checker 会处理主页浮窗，不适合要求完全不操作游戏状态的检查。
"""

from __future__ import annotations

from typing import Any

from autowsgr.application.controller import home
from autowsgr.application.navigation.types import PageName


# 一句话描述 (--list 时显示)
DESC = '链路自检: 连接 + 主页浮窗处理 + 主页识别'


def run(rt: Any) -> bool:
    """执行链路自检步骤。"""
    ctx = rt.ctx  # 框架已绑定 runtime 的 ContextHandle

    screen = rt.action('截图', ctx.runtime.ctrl.screenshot)
    if screen is rt.FAILED:
        return False
    ctx.record_screenshot(screen)

    page = rt.action(
        '检查首页并处理浮窗',
        lambda _ctx: home.read_home_layer(_ctx) == (PageName.HOME,),
        ctx,
    )
    if page is rt.FAILED:
        return False
    if page:
        ctx.set_current_page(PageName.HOME.value)
    ctx.record_result(page)
    rt.note(f'首页模板命中: {page}')
    return rt.check('首页模板命中', lambda: page)
