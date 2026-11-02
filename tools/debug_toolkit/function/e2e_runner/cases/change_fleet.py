"""出征准备页换船 E2E: 首页 -> 出征准备 -> 换船 -> 首页。"""

from __future__ import annotations

import argparse
from typing import Any


DESC = '出征准备换船: OCR 识别并调整指定舰队后返回首页'


def _parse_ships(value: str) -> list[str | None]:
    """Parse a comma-separated fleet and pad it to six slots."""
    names = [name.strip() or None for name in value.split(',')]
    if len(names) > 6:
        raise argparse.ArgumentTypeError('ships 最多支持 6 个槽位')
    if not any(names):
        raise argparse.ArgumentTypeError('ships 至少需要一艘舰船')
    return names + [None] * (6 - len(names))


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register change-fleet case arguments."""
    parser.add_argument('--fleet', type=int, choices=range(1, 5), default=1, help='舰队编号 (1-4)')
    parser.add_argument(
        '--ships',
        type=_parse_ships,
        default=_parse_ships('U-47,U-96'),
        metavar='NAME,...',
        help='目标舰船名，逗号分隔，最多 6 艘',
    )


def run(rt: Any) -> bool:
    """Run the real-device fleet change round trip."""
    if rt.ctx.ocr is None:
        rt.note('换船需要 OCR，请使用 --with-ocr')
        return False

    from autowsgr.application.controller.home import HomePage
    from autowsgr.application.navigation import goto_page
    from autowsgr.application.ui.controller.fleet import BattlePreparationPage
    from autowsgr.common.types import PageName

    ctx = rt.ctx
    if (
        not rt.check(
            '启动后位于主页面',
            lambda: HomePage.check_current_page(ctx.ctrl.screenshot()).matched,
        )
        or rt.action('进入出征准备页', goto_page, ctx, PageName.BATTLE_PREPARATION) is rt.FAILED
    ):
        return False

    if (
        not rt.check(
            '位于出征准备页',
            lambda: BattlePreparationPage.check_current_page(ctx.ctrl.screenshot()).matched,
        )
        or rt.action(
            f'调整第 {rt.args.fleet} 舰队: {rt.args.ships}',
            BattlePreparationPage(ctx).adjust_fleet,
            fleet_id=rt.args.fleet,
            fleet_rules=rt.args.ships,
        )
        is rt.FAILED
    ):
        return False

    if rt.action('返回主页面', goto_page, ctx, PageName.HOME) is rt.FAILED:
        return False
    return rt.check(
        '返回后位于主页面',
        lambda: HomePage.check_current_page(ctx.ctrl.screenshot()).matched,
    )
