"""地图页面 UI 控制器端到端测试。

运行方式::

    python testing/ui/map_page/e2e.py [serial] [--auto] [--debug] [--pause 1.5]

前置条件：
    游戏位于 **地图选择页面** (出征面板)
    （主页面 → 出征）

测试内容：
    1. 验证初始状态 (地图页面, 出征面板)
    2. 读取状态 (远征通知、当前面板)
    3. 面板切换: 出征 → 演习 → 远征 → 战役 → 决战 → 出征
    4. 章节导航: 下一章 → 上一章 (视觉确认)
    5. 地图页面 → ◁ 返回主页面
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
    """执行地图页面控制器完整测试序列。"""
    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.controller.sortie import (
        SortiePage,
        SortieTab,
    )
    from autowsgr.application.controller.sortie.battle import BattlePage
    from autowsgr.application.ui.controller.operations.sortie_page.battle_page import recognition

    sortie_page = SortiePage(runner.ctx)
    battle_page = BattlePage(runner.ctx)

    # ───── Step 0: 验证初始状态 ──────────────────────────────────────
    runner.verify_current('初始验证: sortie_page', '出征页面', SortiePage.check_current_page)
    if runner.aborted:
        return

    # ───── Step 1: 读取状态 ──────────────────────────────────────────
    runner.read_state(
        '地图页面状态',
        readers={
            '远征通知': SortiePage.check_expedition_notification,
            '当前顶部标签': SortiePage.read_active_tab,
            '选中章节Y': recognition._read_selected_chapter_y,
        },
    )

    # ───── Step 2-6: 面板切换 ─────────────────────────────────────────
    panel_sequence = [
        SortieTab.EXERCISE,
        SortieTab.EXPEDITION,
        SortieTab.CAMPAIGN,
        SortieTab.DECISIVE,
        SortieTab.SORTIE,
    ]
    for panel in panel_sequence:
        runner.execute_step(
            f'面板切换 → {panel.value}',
            '出征页面',
            SortiePage.check_current_page,
            lambda p=panel: sortie_page.click_tab(p),
        )
        if runner.aborted:
            return

    # ───── Step 7: 章节 → 下一章 ─────────────────────────────────────
    runner.execute_step(
        '章节 → 下一章',
        '出征页面',
        SortiePage.check_current_page,
        battle_page.click_next_chapter,
    )
    if runner.aborted:
        return

    # ───── Step 8: 章节 → 上一章 ─────────────────────────────────────
    runner.execute_step(
        '章节 → 上一章 (恢复)',
        '出征页面',
        SortiePage.check_current_page,
        battle_page.click_prev_chapter,
    )
    if runner.aborted:
        return

    # ───── Step 9: 地图页面 → ◁ 主页面 ──────────────────────────────
    runner.execute_step(
        '地图页面 → ◁ 主页面',
        '主页面',
        HomePage.check_current_page,
        sortie_page.go_back,
    )


def _navigate_to(ctrl: AndroidController, pause: float) -> None:
    """从任意已知页面导航到地图页面（出征面板）。"""
    import time

    from autowsgr.application.controller.home import HomePage

    if not reset_to_main_page(ctrl, pause):
        return
    screen = ctrl.screenshot()
    if HomePage.check_current_page(screen):
        HomePage(ctrl).navigate_to(HomePage.Target.SORTIE)
        time.sleep(pause)


def main() -> None:
    args = parse_e2e_args(
        '地图页面 (SortiePage) e2e 测试',
        precondition='游戏位于地图选择页面 (出征面板)，从主页面→出征进入',
        default_log_dir='logs/e2e/map_page',
    )
    ctrl = connect_via_launcher(args.serial, args.log_dir, args.log_level)
    from loguru import logger

    logger.info('=== 地图页面 e2e 测试开始 ===')
    from autowsgr.application.controller.sortie import SortiePage

    if not ensure_page(
        ctrl,
        SortiePage.check_current_page,
        lambda: _navigate_to(ctrl, args.pause),
        '出征页面',
        auto_mode=args.auto,
        pause=args.pause,
    ):
        ctrl.disconnect()
        sys.exit(1)
    runner = UIControllerTestRunner(
        ctrl,
        controller_name='出征页面',
        log_dir=args.log_dir,
        auto_mode=args.auto,
        pause=args.pause,
    )
    try:
        run_test(runner)
    except KeyboardInterrupt:
        from testing.ui._framework import warn

        warn('用户中断 (Ctrl+C)')
    except Exception as exc:
        from testing.ui._framework import fail

        fail(f'未预期异常: {exc}')
        logger.opt(exception=True).error('地图页面 e2e 测试异常')
    finally:
        runner.finalize()
        runner.print_summary()
        ctrl.disconnect()
        info('设备已断开')

    logger.info('=== 地图页面 e2e 测试结束 ===')
    r = runner.report
    sys.exit(1 if (r.failed > 0 or r.errors > 0) else 0)


if __name__ == '__main__':
    main()
