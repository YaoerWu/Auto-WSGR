"""演习链路 E2E — 按指定顺序反复选对手、进准备页、退回演习页。

设计：
1. 先建栈（任意状态 → 主页 → 演习页），之后每步都从栈顶出发。
2. 按给定顺序逐个对手执行三段：选对手进浮窗 → 点挑战进准备页 → 回退。
3. 每次回退后校验栈顶必须落在演习页——这是「准备页退出回演习页、不回浮窗」
   这条规则的实机证据。
4. 一步失败即停：栈已经不可信，继续走只会带病往下。

用法::

    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch exercise_chain
    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch exercise_chain --orders 12345,54321
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DESC = '演习链路: 按顺序选对手 → 进准备页 → 退回，验证栈落点'

# 用户指定的覆盖顺序：正序、逆序、以及四种跨位跳跃。
DEFAULT_ORDERS = ('12345', '54321', '23451', '34512', '45123', '53214')

OUTPUT_ROOT = Path(r'C:\ShiinaKuroko\01.Project\debug\nav\exercise_chain')


def add_arguments(parser: Any) -> None:
    """定义 case 专属参数。"""
    parser.add_argument(
        '--orders',
        default=','.join(DEFAULT_ORDERS),
        help='对手顺序，逗号分隔，每段由 1-5 组成',
    )


def run(rt: Any) -> bool:
    """按顺序跑完每段「选对手 → 进准备页 → 回退」。"""
    from autowsgr.application.navigation.service import NavigationService
    from autowsgr.application.navigation.types import PageName
    from autowsgr.dispatch.session import get_session

    ctx = rt.ctx
    session = get_session()
    navigator = NavigationService(ctx, session=session)

    orders = [part.strip() for part in rt.args.orders.split(',') if part.strip()]
    if not orders:
        raise ValueError('--orders 不能为空')
    for order in orders:
        if any(digit not in '12345' for digit in order):
            raise ValueError(f'对手顺序只能由 1-5 组成，收到 {order!r}')

    started = time.monotonic()
    for label, target in (('回到主页', PageName.HOME), ('切到演习页', PageName.EXERCISE)):
        t0 = time.monotonic()
        navigator.navigate_to(target)
        print(f'PASS 前置：{label}  {int((time.monotonic() - t0) * 1000)}ms', flush=True)

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for order_index, order in enumerate(orders, start=1):
        for step_index, rival in enumerate(order, start=1):
            label = f'顺序{order_index}/{len(orders)} 第{step_index}/{len(order)}个: 对手{rival}'
            t0 = time.monotonic()
            detail: dict[str, Any] = {
                'order': order,
                'rival': int(rival),
                'ok': False,
                'ms': 0,
            }
            try:
                navigator.navigate_to(PageName.EXERCISE_PREPARATION, rival=int(rival))
                navigator.navigate_back()
                session_page = session.current_page()
                if session_page != PageName.EXERCISE.value:
                    raise RuntimeError(f'回退后栈顶应为演习页，实际 {session_page!r}')
                detail['ok'] = True
            except Exception as exc:
                detail['error'] = f'{type(exc).__name__}: {exc}'
                failures.append(detail)
                records.append(detail)
                elapsed = int((time.monotonic() - t0) * 1000)
                detail['ms'] = elapsed
                print(f'FAIL {label}  {elapsed}ms  {detail["error"]}', flush=True)
                break
            elapsed = int((time.monotonic() - t0) * 1000)
            detail['ms'] = elapsed
            records.append(detail)
            print(f'PASS {label}  {elapsed}ms', flush=True)
        if failures:
            break

    total_ms = int((time.monotonic() - started) * 1000)
    done = sum(1 for record in records if record['ok'])
    print(flush=True)
    print('=' * 72, flush=True)
    print(f'顺序 {len(orders)} 段  完成 {done}  失败 {len(failures)}', flush=True)
    print(f'总耗时 {total_ms / 1000:.1f}s', flush=True)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        'orders': orders,
        'done': done,
        'failed': len(failures),
        'total_ms': total_ms,
        'records': records,
        'failures': failures,
    }
    stamp = time.strftime('%Y%m%d_%H%M%S')
    report_path = OUTPUT_ROOT / f'exercise_chain_{stamp}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'报告: {report_path}', flush=True)

    return not failures


__all__: list[str] = []
