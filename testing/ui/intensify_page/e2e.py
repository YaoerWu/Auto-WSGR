"""强化页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/intensify_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **强化页面** (侧边栏 → 强化)

测试内容：
    1. 验证初始强化页面
    2. 强化页面 → ◁ 侧边栏
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import TYPE_CHECKING

from testing.ui._framework import (
    UIControllerTestRunner,
    connect_via_launcher,
    ensure_page,
    info,
    parse_e2e_args,
    reset_to_main_page,
)


if TYPE_CHECKING:
    from autowsgr.common.device import AndroidController


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.application.controller.sidebar import SidebarPage
    from autowsgr.application.controller.sidebar.intensify import IntensifyPage

    intensify_page = IntensifyPage(runner.ctrl)

    runner.verify_current('初始验证: 强化页面', '强化页面', IntensifyPage.check_current_page)
    if runner.aborted:
        return

    runner.execute_step(
        '强化页面 → ◁ 侧边栏',
        '侧边栏',
        SidebarPage.check_current_page,
        intensify_page.go_back,
    )


def _navigate_to(ctrl: AndroidController, pause: float) -> None:
    """从任意已知页面导航到强化页面。"""
    import time

    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.controller.sidebar import SidebarPage

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if HomePage.check_current_page(screen):
        HomePage(ctrl).navigate_to(HomePage.Target.SIDEBAR)
        time.sleep(pause)
        screen = ctrl.screenshot()
    if SidebarPage.check_current_page(screen):
        SidebarPage(ctrl).go_to_intensify()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '强化页面 (IntensifyPage) e2e 测试',
        precondition='游戏位于强化页面 (侧边栏 → 强化)',
        default_log_dir='logs/e2e/intensify_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 强化页面 e2e 测试开始 ===')
    from autowsgr.application.controller.sidebar.intensify import IntensifyPage

    if not ensure_page(
        ctrl,
        IntensifyPage.check_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '强化页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='强化页面',
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        from testing.ui._framework import warn

        warn('用户中断')
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f'未预期: {exc}')
        logger.opt(exception=True).error('强化页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
