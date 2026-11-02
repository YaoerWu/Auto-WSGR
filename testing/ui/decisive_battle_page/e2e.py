"""决战页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/decisive_battle_page/e2e.py [serial] [--auto] [--debug]

前置条件：
    游戏位于 **决战总览页面** (地图 → 决战面板 → 点击进入)

测试内容：
    1. 验证初始状态
    2. 向前翻一章 (click_previous_chapter)，再向后翻一章还原 (click_next_chapter)
    3. 决战页面 → ◁ 主页面
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
    from autowsgr.application.runtime.context import GameContext
    from autowsgr.common.device import AndroidController


def _build_context(ctrl: AndroidController) -> GameContext:
    """为实机脚本构造只用于页面点击的上下文。"""
    from autowsgr.application.runtime.context import GameContext
    from autowsgr.config import UserConfig

    return GameContext(ctrl=ctrl, config=UserConfig(), ocr=None)  # type: ignore[arg-type]


def run_test(runner: UIControllerTestRunner) -> None:
    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.page import (
        DecisiveBattlePage,
    )

    db_page = DecisiveBattlePage(_build_context(runner.ctrl), ocr=None)

    runner.verify_current('初始验证: 决战页面', '决战页面', DecisiveBattlePage.check_current_page)
    if runner.aborted:
        return

    runner.execute_step(
        '决战页面 → ◁ 前一章节',
        '决战页面',
        DecisiveBattlePage.check_current_page,
        db_page.click_previous_chapter,
    )
    if runner.aborted:
        return

    runner.execute_step(
        '决战页面 → ▷ 后一章节 (还原)',
        '决战页面',
        DecisiveBattlePage.check_current_page,
        db_page.click_next_chapter,
    )
    if runner.aborted:
        return

    runner.execute_step(
        '决战页面 → ◁ 主页面',
        '主页面',
        HomePage.check_current_page,
        db_page.go_back,
    )


def _navigate_to(ctrl: AndroidController, pause: float) -> None:
    """从任意已知页面导航到决战总览。"""
    import time

    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.controller.sortie import (
        SortiePage,
        SortieTab,
    )
    from autowsgr.application.ui.controller.operations.sortie_page.decisive_page import (
        DecisiveEntryPage,
    )

    ctx = _build_context(ctrl)
    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if HomePage.check_current_page(screen):
        HomePage(ctx).navigate_to(HomePage.Target.SORTIE)
        time.sleep(pause)
        screen = ctrl.screenshot()
    if SortiePage.check_current_page(screen):
        if SortiePage.read_active_tab(screen) != SortieTab.DECISIVE:
            SortiePage(ctx).click_tab(SortieTab.DECISIVE)
            time.sleep(pause)
            screen = ctrl.screenshot()
        DecisiveEntryPage(ctx).enter_decisive()
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '决战页面 (DecisiveBattlePage) e2e 测试',
        precondition='游戏位于决战总览页面 (地图 → 决战面板 → 点击进入)',
        default_log_dir='logs/e2e/decisive_battle_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 决战页面 e2e 测试开始 ===')
    from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.page import (
        DecisiveBattlePage,
    )

    if not ensure_page(
        ctrl,
        DecisiveBattlePage.check_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '决战页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='决战页面',
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
        logger.opt(exception=True).error('决战页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
