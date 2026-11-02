"""导航链路 E2E — 一条长链路串起全部导航边。

设计（按用户方法）：
1. 先建立栈：从未知位置 navigate_to(HOME) 一次，栈就变成了"我知道我在哪"；
   之后每次导航都读栈顶，不再遍历识别，快且稳。
2. 栈一旦可信，就可以把导航编排成一条长链路，来回穿插各个域；
   每一步都是"从上一站到下一站"，步与步之间靠到达确认串起来。
3. 每一步都验证到达才继续，所以一步错不会污染后面的步骤。

用法::

    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch nav_chain
    python tools/debug_toolkit/main.py e2e --serial emulator-5554 --no-launch nav_chain --from-login
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DESC = '导航链路: 建栈后一条长链路串起全部边，统计覆盖率'

# 一条覆盖各域的长链路：每一步都是「从当前页走到下一站」。
# 回主页统一经过每日浮窗链（公告 → 奖励 → 奖励确认 → 主页），因此链路上
# 按需要插入 HOME，让"回主页"成为真实的一步而不是隐含行为。
CHAIN = (
    'HOME',  # 起点（建栈后）
    # ── 后院域：主页进出 + 四个二级页互跳（跨二级页经后院主页中转）──
    'BACKYARD',
    'CANTEEN',
    'BACKYARD',
    'BATH',
    'BACKYARD',
    'ACADEMY',
    'BACKYARD',
    'RANK_ROOM',
    'BACKYARD',
    'HOME',
    # ── 侧边栏域：三个二级菜单，各自进出 ──
    'SIDEBAR',
    'BUILD_SUBMENU',
    'BUILD',
    'HOME',
    'SIDEBAR',
    'INTENSIFY_SUBMENU',
    'INTENSIFY',
    'HOME',
    'SIDEBAR',
    'FRIEND',
    'HOME',
    # ── 任务域：主页 + 奖励浮窗往返 ──
    'MISSION',
    'MISSION_REWARD_CONFIRM',
    'MISSION',
    'HOME',
    # ── 出征域 ──
    'SORTIE_MAP',
    'HOME',
    # ── 活动域 ──
    # 活动未开放期间先注释掉；开放后恢复下面三步（末行 HOME 是活动回主页）。
    # 'EVENT_MAP',
    # 'EVENT_STAGE_OVERLAY',
    # 'EVENT_MAP',
    # 'HOME',
)

# 登录段：游戏冷启动后才能跑（登录页 ↔ 区服选择页 ↔ 主页）。
LOGIN_CHAIN = (
    'LOGIN_PAGE',
    'SERVER_SELECT',
    'LOGIN_PAGE',
    'HOME',
)

OUTPUT_ROOT = Path(r'C:\ShiinaKuroko\01.Project\debug\nav\chain')


def add_arguments(parser: Any) -> None:
    """case 专属参数。"""
    parser.add_argument(
        '--from-login',
        action='store_true',
        help='从登录页开始（需要游戏停在登录页或 --cold 冷启动）',
    )
    parser.add_argument(
        '--popups-settled',
        action='store_true',
        help='注入「今天已确认不会再弹每日浮窗」标记（今天已处理过时用）',
    )


def run(rt: Any) -> bool:
    """建栈后按链路逐步导航，并统计边覆盖率。"""
    from autowsgr.application.navigation import registry
    from autowsgr.application.navigation.service import NavigationService
    from autowsgr.application.navigation.types import PageName
    from autowsgr.dispatch.session import DailyPopup, get_session

    ctx = rt.ctx
    session = get_session()
    navigator = NavigationService(ctx, session=session)

    if rt.args.popups_settled:
        # 注入生产同款标记：三个浮窗都当作今天已处理，回主页时各自跳过识别。
        for popup in DailyPopup:
            session.mark_popup_settled(popup)
        rt.note('已注入每日浮窗处理标记（三个浮窗）')

    # 域探针负责的页面不登记到逐页注册表，统计边覆盖时要一并算上。
    nodes = list(PageName)
    all_edges = {edge.description for p in nodes for edge in registry.get_targets(p)}

    # 导航栈由 navigate_to 自己维护：第一次调用识别当前页并压栈，之后每跳接着压。
    # 测试只调用生产入口，不额外发明步骤。
    chain = LOGIN_CHAIN if rt.args.from_login else CHAIN
    walked: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    started = time.monotonic()

    for index, name in enumerate(chain, start=1):
        target = PageName[name]
        # 栈空（第一跳）时导航器会自己识别当前页并压栈，这里不预读、也不编造步骤。
        source = session.current_page()
        path = registry.find_path(PageName(source), target) if source is not None else ()

        edges = [edge.description for edge in path]
        t0 = time.monotonic()
        try:
            navigator.navigate_to(target)
            elapsed = int((time.monotonic() - t0) * 1000)
            for desc in edges:
                walked[desc] = walked.get(desc, 0) + 1
            label = source if source is not None else '(栈空)'
            records.append(
                {'from': label, 'to': name, 'steps': len(path), 'ok': True, 'ms': elapsed}
            )
            print(
                f'PASS [{index}/{len(chain)}] {label} -> {name} ({len(path)}步)  {elapsed}ms',
                flush=True,
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            detail = {
                'from': source,
                'to': name,
                'steps': len(path),
                'ok': False,
                'ms': elapsed,
                'error': f'{type(exc).__name__}: {exc}',
                'edges': edges,
            }
            failures.append(detail)
            records.append(detail)
            print(
                f'FAIL [{index}/{len(chain)}] {source} -> {name}  {elapsed}ms  {detail["error"]}',
                flush=True,
            )
            print(f'     路径: {edges}', flush=True)
            # 链路断在这里：栈已经不可信，继续走只会带病往下，直接停。
            break

    total_ms = int((time.monotonic() - started) * 1000)
    missed = sorted(all_edges - set(walked))

    print(flush=True)
    print('=' * 72, flush=True)
    print(
        f'链路 {len(chain)} 步  完成 {len(records) - len(failures)}  失败 {len(failures)}',
        flush=True,
    )
    print(f'边覆盖 {len(walked)} / {len(all_edges)}', flush=True)
    if missed:
        print('未走到的边:', flush=True)
        for desc in missed:
            print(f'  {desc}', flush=True)
    else:
        print('未走到的边: 无（全边覆盖）', flush=True)
    print(f'总耗时 {total_ms / 1000:.1f}s', flush=True)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        'chain_len': len(chain),
        'done': len(records) - len(failures),
        'failed': len(failures),
        'edge_total': len(all_edges),
        'edge_walked': len(walked),
        'edge_missed': missed,
        'edge_hits': walked,
        'total_ms': total_ms,
        'records': records,
        'failures': failures,
    }
    stamp = time.strftime('%Y%m%d_%H%M%S')
    report_path = OUTPUT_ROOT / f'chain_{stamp}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'报告: {report_path}', flush=True)

    return len(failures) == 0
