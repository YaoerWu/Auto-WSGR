"""食堂页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/canteen_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **食堂页面** (后院 → 食堂)

测试内容：
    1. 验证初始状态
    2. 食堂页面 → ◁ 后院
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
    from autowsgr.application.controller.backyard import BackyardPage
    from autowsgr.application.controller.backyard.canteen import CanteenPage

    canteen_page = CanteenPage(runner.ctx)

    runner.verify_current('初始验证: 食堂页面', '食堂页面', CanteenPage.check_current_page)
    if runner.aborted:
        return

    runner.execute_step(
        '食堂页面 → ◁ 后院',
        '后院',
        BackyardPage.check_current_page,
        canteen_page.go_back,
    )


def _navigate_to(ctrl: AndroidController, pause: float) -> None:
    """从任意已知页面导航到食堂页面。"""
    import time

    from autowsgr.application.controller.backyard import BackyardPage
    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.runtime.context import GameContext
    from autowsgr.config import UserConfig

    if not reset_to_main_page(ctrl, pause):
        return
    ctx = GameContext(ctrl=ctrl, config=UserConfig())
    screen = ctrl.screenshot()
    if HomePage.check_current_page(screen):
        HomePage(ctx).go_to_backyard()
        time.sleep(pause)
        screen = ctrl.screenshot()
    if BackyardPage.check_current_page(screen):
        BackyardPage(ctx).go_to_canteen()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '食堂页面 (CanteenPage) e2e 测试',
        precondition='游戏位于食堂页面 (后院 → 食堂)',
        default_log_dir='logs/e2e/canteen_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 食堂页面 e2e 测试开始 ===')
    from autowsgr.application.controller.backyard.canteen import CanteenPage

    if not ensure_page(
        ctrl,
        CanteenPage.check_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '食堂页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='食堂页面',
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
        logger.opt(exception=True).error('食堂页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
