"""每日浮窗上下文记录验证 — 空栈起步，逐段确认处理结果有没有记进程序级上下文。

场景（运行前请在模拟器上摆好）::

    底层：主页
    中层：侧边栏
    上层：每日奖励浮窗

跑法::

    python tools/debug_toolkit/main.py e2e --no-launch popup_context

设计：只从业务语义出发断言——「事实上处理过浮窗」之后，程序级上下文
（`SessionState.popup_settled`）就应当被记录，后续经过主页不必重复探测。三个浮窗彼此解耦，各记各的。
"""

from __future__ import annotations

import time
from typing import Any


DESC = '每日浮窗上下文记录: 空栈起步，逐段检查「处理过浮窗」有没有被记进上下文'


def _flags(session: Any) -> str:
    """把三个浮窗标记的当前状态拼成一行。"""
    from autowsgr.dispatch.session import DailyPopup

    return ' '.join(f'{popup.value}={session.popup_settled(popup)}' for popup in DailyPopup)


def run(rt: Any) -> bool:
    """按场景逐段导航，每步打印上下文状态。"""
    from autowsgr.application.navigation.service import NavigationService
    from autowsgr.application.navigation.types import PageName
    from autowsgr.dispatch.session import DailyPopup, get_session

    session = get_session()
    # 空栈 + 空浮窗标记起步（标记按天记录，新进程天然为空，不注入 --popups-settled）。
    session.clear_pages()
    rt.note(f'起点: 栈={session.current_page()!r}, 标记={_flags(session)}')

    navigator = NavigationService(rt.ctx, session=session)

    def walk(label: str, target: PageName) -> bool:
        """走一步，并打印这一步之后的上下文状态与耗时。"""
        started = time.monotonic()
        error: str | None = None
        try:
            navigator.navigate_to(target)
        except Exception as exc:  # 失败也要把上下文状态打出来
            error = f'{type(exc).__name__}: {exc}'
        elapsed = int((time.monotonic() - started) * 1000)
        mark = 'FAIL' if error else 'PASS'
        print(
            f'  [{mark}] {label}  {elapsed}ms  '
            f'栈顶={session.current_page()!r}  标记={_flags(session)}',
            flush=True,
        )
        if error:
            print(f'         {error}', flush=True)
        return error is None

    ok = True

    # ① 空栈起步：场景里主页上盖着侧边栏与奖励浮窗，这一跳应当把奖励浮窗处理掉并记录。
    ok &= walk('空栈 → HOME（应处理奖励浮窗）', PageName.HOME)
    ok &= rt.check(
        '处理奖励浮窗后 REWARD 标记已记录', lambda: session.popup_settled(DailyPopup.REWARD)
    )

    # ② 浮窗清掉之后，侧边栏应当可以直接操作。
    ok &= walk('HOME → SIDEBAR（浮窗清掉后侧边栏可用）', PageName.SIDEBAR)

    # ③ 随便去一个主页以外的页面。
    ok &= walk('SIDEBAR → BACKYARD（离开主页）', PageName.BACKYARD)

    # ④ 回到主页：这一跳应当处理每日公告并记录。
    ok &= walk('BACKYARD → HOME（应处理每日公告）', PageName.HOME)
    ok &= rt.check('处理每日公告后 NEWS 标记已记录', lambda: session.popup_settled(DailyPopup.NEWS))

    # ⑤ 再走一次 home → X → home，确认记录稳定、不再重复处理。
    ok &= walk('HOME → MISSION（再离开一次）', PageName.MISSION)
    ok &= walk('MISSION → HOME（复查上下文）', PageName.HOME)
    ok &= rt.check(
        '第二轮之后两个标记仍然记录着',
        lambda: session.popup_settled(DailyPopup.NEWS) and session.popup_settled(DailyPopup.REWARD),
    )

    return ok
