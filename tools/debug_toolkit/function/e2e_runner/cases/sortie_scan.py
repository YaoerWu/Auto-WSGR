"""出征全节点 E2E — 按（章节 x 节点）逐个导航到出征准备页。

设计：
1. 先从主页导航到出征页，建好导航栈；之后每一步都从栈顶出发。
2. 再按地图表里的全量（章节，节点）组合逐个调用
   navigate_to(BATTLE_PREPARATION, chapter=..., map_id=...)，每次都是真实的
   「选章选节 → 点进入出征准备」，到达确认由导航器负责。
3. 每进一次准备页就退回到出征页，为下一个组合腾出起点。
4. 一步失败即停：栈已经不可信，继续走只会带病往下。

用法::

    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch sortie_scan
    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch sortie_scan --chapters 1,2
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any


DESC = '出征全节点: 按章节 x 节点逐个导航到出征准备页'

OUTPUT_ROOT = Path(r'C:\ShiinaKuroko\01.Project\debug\nav\sortie_scan')


def add_arguments(parser: Any) -> None:
    """case 专属参数。"""
    parser.add_argument('--chapters', default='', help='只跑这些章节，逗号分隔；默认全部')
    parser.add_argument('--nodes', default='', help='只跑这些节点号，逗号分隔；默认全量')
    parser.add_argument('--keep-going', action='store_true', help='单步失败后尝试回退并继续')
    parser.add_argument('--shuffle', action='store_true', help='打乱组合顺序，模拟随机跳转')
    parser.add_argument('--seed', type=int, default=0, help='--shuffle 的随机种子，0 表示每次不同')


def _parse_ids(text: str) -> set[int]:
    """把逗号分隔的编号解析成集合。"""
    return {int(part) for part in text.split(',') if part.strip()}


def run(rt: Any) -> bool:
    """按（章节 x 节点）逐个进入出征准备页。"""
    from autowsgr.application.controller.sortie.battle.checker import MAP_DATABASE
    from autowsgr.application.ui.navigation.service import NavigationService
    from autowsgr.application.ui.navigation.types import NavigationError, PageName
    from autowsgr.dispatch.session import get_session

    ctx = rt.ctx
    session = get_session()
    navigator = NavigationService(ctx, session=session)

    chapters = _parse_ids(rt.args.chapters)
    nodes = _parse_ids(rt.args.nodes)
    combos = [
        (chapter, map_id)
        for chapter, map_id in sorted(MAP_DATABASE)
        if (not chapters or chapter in chapters) and (not nodes or map_id in nodes)
    ]
    if rt.args.shuffle:
        random.seed(rt.args.seed or None)
        random.shuffle(combos)
    print(f'组合 {len(combos)} 个：{combos}', flush=True)

    # 建栈：之后每步都读栈顶，不再遍历识别。
    started = time.monotonic()
    try:
        navigator.navigate_to(PageName.HOME)
        navigator.navigate_to(PageName.SORTIE_MAP)
    except Exception as exc:
        print(f'FAIL 前置导航 {type(exc).__name__}: {exc}', flush=True)
        return False
    print(
        f'PASS 前置导航 HOME -> SORTIE_MAP  {int((time.monotonic() - started) * 1000)}ms',
        flush=True,
    )

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, (chapter, map_id) in enumerate(combos, start=1):
        t0 = time.monotonic()
        try:
            navigator.navigate_to(
                PageName.BATTLE_PREPARATION,
                chapter=chapter,
                map_id=map_id,
            )
            navigator.navigate_back()
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            detail = {
                'chapter': chapter,
                'map_id': map_id,
                'ok': False,
                'ms': elapsed,
                'error': f'{type(exc).__name__}: {exc}',
            }
            failures.append(detail)
            records.append(detail)
            print(
                f'FAIL [{index}/{len(combos)}] {chapter}-{map_id}  {elapsed}ms  {detail["error"]}',
                flush=True,
            )
            if not rt.args.keep_going:
                break
            # 回退一步把栈拉回出征页；恢复不了就让下一轮自己失败。
            try:
                navigator.navigate_back()
            except NavigationError as exc:
                print(f'      回退失败: {exc}', flush=True)
            continue
        elapsed = int((time.monotonic() - t0) * 1000)
        records.append({'chapter': chapter, 'map_id': map_id, 'ok': True, 'ms': elapsed})
        print(f'PASS [{index}/{len(combos)}] {chapter}-{map_id}  {elapsed}ms', flush=True)

    total_ms = int((time.monotonic() - started) * 1000)
    print(flush=True)
    print('=' * 72, flush=True)
    print(
        f'组合 {len(combos)}  完成 {len(records) - len(failures)}  失败 {len(failures)}',
        flush=True,
    )
    print(f'总耗时 {total_ms / 1000:.1f}s', flush=True)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        'combo_total': len(combos),
        'done': len(records) - len(failures),
        'failed': len(failures),
        'total_ms': total_ms,
        'records': records,
        'failures': failures,
    }
    stamp = time.strftime('%Y%m%d_%H%M%S')
    report_path = OUTPUT_ROOT / f'scan_{stamp}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'报告: {report_path}', flush=True)

    return len(failures) == 0
