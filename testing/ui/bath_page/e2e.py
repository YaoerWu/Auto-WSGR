"""模块功能：执行浴室页面 UI Controller 的端到端验证。

上层调用：
- testing.ui._framework：提供实机测试运行器、页面保障和报告输出。

下层依赖：
- backyard.bath_page：提供浴室页面检查和页面级返回入口。
- backyard.main_page、home.main_page：提供实机测试前置导航。

边界：
本模块只连接真实设备验证页面行为，不承载生产业务流程或运行时状态。

运行方式：
    python testing/ui/bath_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于浴室页面（后院 → 浴室）。

测试内容：
    1. 验证初始状态。
    2. 读取页面状态（当前修理槽信息）。
    3. 浴室页面 → 后院。
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
    from autowsgr.application.controller.backyard.bath import BathPage

    bath_page = BathPage(runner.ctrl)

    runner.verify_current('初始验证: 浴室页面', '浴室页面', BathPage.check_current_page)
    if runner.aborted:
        return

    runner.read_state(
        '浴室页面',
        readers={'修理中船舰数': lambda _s: '（需手动读取）'},
    )

    runner.execute_step(
        '浴室页面 → ◁ 后院',
        '后院',
        BackyardPage.check_current_page,
        bath_page.go_back,
    )


def _navigate_to(ctrl: AndroidController, pause: float) -> None:
    """从任意已知页面导航到浴室页面。"""
    import time

    from autowsgr.application.controller.backyard import BackyardPage
    from autowsgr.application.controller.home import HomePage

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if HomePage.check_current_page(screen):
        HomePage(ctrl).go_to_backyard()
        time.sleep(pause)
        screen = ctrl.screenshot()
    if BackyardPage.check_current_page(screen):
        BackyardPage(ctrl).go_to_bath()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '浴室页面 (BathPage) e2e 测试',
        precondition='游戏位于浴室页面 (后院 → 浴室)',
        default_log_dir='logs/e2e/bath_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 浴室页面 e2e 测试开始 ===')
    from autowsgr.application.controller.backyard.bath import BathPage

    if not ensure_page(
        ctrl,
        BathPage.check_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '浴室页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='浴室页面',
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
        logger.opt(exception=True).error('浴室页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
