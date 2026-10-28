"""断点演练 E2E — 在导航链的每一个断点上触发三种让路。

设计:

1. 断点位置由导航器自己决定, 所以本 case 不预设位置, 而是给
   ContextHandle.check_interrupt 打桩, 记录每次断点落在哪个文件的哪一行。
   「每一个断点都被检测到」由覆盖到的位置集合来证明。
2. 三个维度按 dispatch 的真实语义区分:
   - 终止 (stop): 抛 TaskStopped, 执行器清栈回主页, 任务不能原地恢复。
   - 恢复 (restore): 插队让路, 栈保留; 让路结束后从栈顶算剩余路径继续。
   - 暂停重启 (restart): 用户暂停, 处理器清栈; 恢复时按实时识别重建栈再继续。
3. 先跑一遍不注入的探测轮, 记下这条链路上实际出现的全部断点位置; 之后每个
   维度逐个位置注入, 让每一类断点都被真正打断过, 而不是只统计到。
   链路上额外插一站出征准备页: 注册表里「选完章、进准备页之前」的连续动作
   断点只在那一站出现; 回退断点只在 navigate_back 时出现, 所以位置迟迟没被
   触发时会额外补一次回退。

用法::

    python tools/debug_toolkit/main.py e2e checkpoint_drill --steps 3
    python tools/debug_toolkit/main.py e2e checkpoint_drill --dimension stop --skip-detect
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tools.debug_toolkit.function.e2e_runner.cases.nav_chain import CHAIN


if TYPE_CHECKING:
    from autowsgr.dispatch.context import InterruptSignals


DESC = '断点演练: 逐断点触发终止/恢复/暂停重启, 覆盖 nav_chain 全链路'

OUTPUT_ROOT = Path(r'C:\ShiinaKuroko\01.Project\debug\nav\checkpoint')

_DIMENSIONS = ('stop', 'restore', 'restart')
"""让路语义三选一, 与 dispatch.processor 对三种打断的处理一一对应。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 插桩: 记录断点位置 + 按位置注入信号
# ═══════════════════════════════════════════════════════════════════════════════


class _InterruptProbe:
    """代理 ContextHandle.check_interrupt: 记账位置, 并在指定位置置位信号。"""

    def __init__(self, ctx: Any, signals: InterruptSignals) -> None:
        self.sites: list[str] = []
        self.fired = False
        self._signals = signals
        self._kind: str | None = None
        self._site: str | None = None
        self._origin = ctx.check_interrupt
        ctx.check_interrupt = self

    def arm(self, kind: str | None, site: str | None) -> None:
        """准备一轮: kind 为 None 只记账; site 指定只在哪个位置注入。"""
        self._kind = kind
        self._site = site
        self.fired = False
        self.sites.clear()

    def disarm(self) -> None:
        """本轮结束, 后面即使还有断点也不再注入。"""
        self._kind = None

    def take_sites(self) -> list[str]:
        """取走这一轮记录到的断点位置。"""
        taken = list(self.sites)
        self.sites.clear()
        return taken

    def __call__(self) -> None:
        frame = sys._getframe(1)
        # 执行器用 _check_interrupt() 包了一层, 要剥到真正的调用点才有区分度。
        while frame is not None and frame.f_code.co_name == '_check_interrupt':
            frame = frame.f_back
        site = ''
        if frame is not None:
            site = f'{Path(frame.f_code.co_filename).name}:{frame.f_lineno}'
        self.sites.append(site)
        if self._kind is not None and not self.fired and site == self._site:
            self.fired = True
            if self._kind == 'stop':
                self._signals.stop.set()
            else:
                self._signals.pause.set()
        self._origin()


# ═══════════════════════════════════════════════════════════════════════════════
# 最小执行器: 只做一次导航, 让断点穿过生产代码路径
# ═══════════════════════════════════════════════════════════════════════════════


def _make_executor(rt: Any, *, target: Any = None, params: dict[str, Any] | None = None) -> Any:
    """构造一次性的演练执行器 (子类在函数内定义, 避免模块导入即加载导航层)。

    target 为 None 表示回退一步, 用来打出只在 navigate_back 路径上出现的断点。
    """
    from autowsgr.application.ui.navigation.service import NavigationService
    from autowsgr.dispatch.executor import BaseExecutor

    class _DrillExecutor(BaseExecutor):
        """把「导航一步」当成一次任务: 断点的收尾逻辑全走生产代码。"""

        def __init__(self) -> None:
            super().__init__(
                rt.ctx,
                params or {},
                task_type='checkpoint_drill',
                pause=rt.interrupt.pause,
                stop=rt.interrupt.stop,
            )
            self._target = target

        def _execute(self) -> None:
            navigator = NavigationService(self.ctx)
            if self._target is None:
                navigator.navigate_back()
            else:
                navigator.navigate_to(self._target, **self.params)

    return _DrillExecutor()


# ═══════════════════════════════════════════════════════════════════════════════
# 链路
# ═══════════════════════════════════════════════════════════════════════════════


def _steps() -> tuple[tuple[str, dict[str, Any]], ...]:
    """把 nav_chain 的链路摊成 (页面名, 导航入参), 并插入出征准备页一站。"""
    steps: list[tuple[str, dict[str, Any]]] = [(name, {}) for name in CHAIN]
    at = CHAIN.index('SORTIE_MAP')
    # 出征准备页是链路上唯一带入参的目标站, 也是注册表连续动作断点的唯一出口。
    steps[at + 1 : at + 1] = [
        ('BATTLE_PREPARATION', {'chapter': 1, 'map_id': 1}),
        ('SORTIE_MAP', {}),
    ]
    return tuple(steps)


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def add_arguments(parser: Any) -> None:
    """case 专属参数。"""
    parser.add_argument('--steps', type=int, default=0, help='只跑链路前 N 步 (0 = 全跑)')
    parser.add_argument(
        '--dimension',
        action='append',
        choices=_DIMENSIONS,
        help='只跑指定维度, 可重复; 不传则三个都跑',
    )
    parser.add_argument(
        '--skip-detect',
        action='store_true',
        help='跳过探测轮 (维度分开跑时用, 位置改从注入轮次里汇总)',
    )


def run(rt: Any) -> bool:
    """按维度逐断点注入让路信号, 记录断点覆盖与恢复结果。"""
    from autowsgr.application.ui.navigation.service import NavigationService
    from autowsgr.application.ui.navigation.types import PageName
    from autowsgr.dispatch.session import get_session

    dimensions = rt.args.dimension or list(_DIMENSIONS)
    steps = _steps()
    if rt.args.steps > 0:
        steps = steps[: rt.args.steps]

    session = get_session()
    probe = _InterruptProbe(rt.ctx, rt.interrupt)
    navigator = NavigationService(rt.ctx, session=session)

    rt.note(f'链路 {len(steps)} 步, 维度 {", ".join(dimensions)}')
    started = time.monotonic()

    if rt.args.skip_detect:
        detect = {'name': 'detect', 'ok': True, 'sites': [], 'failures': [], 'skipped': True}
    else:
        detect = _run_detect(rt, navigator, probe, PageName, steps, session)

    known_sites = sorted(set(detect['sites']))
    records = [detect]
    records.extend(
        _run_dimension(rt, probe, PageName, session, steps, item, known_sites)
        for item in dimensions
    )

    covered = sorted({site for item in records for site in item.get('sites', []) if site})
    executor_sites = [site for site in covered if site.startswith('executor.py')]
    registry_sites = [site for site in covered if site.startswith('registry.py')]
    detected_all = len(executor_sites) >= 3 and len(registry_sites) >= 1
    injected = sorted(
        {
            item['site']
            for rec in records
            for item in rec.get('attempts', [])
            if item.get('fired') and item.get('site')
        }
    )
    failed = [item for item in records if not item['ok']]
    total_ms = int((time.monotonic() - started) * 1000)

    print(flush=True)
    print('=' * 72, flush=True)
    print(
        f'断点位置 {len(covered)} 个 '
        f'(executor {len(executor_sites)}, registry {len(registry_sites)})',
        flush=True,
    )
    for site in covered:
        print(f'  {site}', flush=True)
    print(f'被真正打断过的位置 {len(injected)} 个: {injected}', flush=True)
    missed = [site for site in covered if site not in injected]
    if missed:
        print(f'只检测到但没打断过的位置: {missed}', flush=True)
    print(f'四类断点全部检测到: {"是" if detected_all else "否"}', flush=True)
    for item in records:
        mark = 'PASS' if item['ok'] else 'FAIL'
        print(f'  [{mark}] {item["name"]}', flush=True)
    print(f'总耗时 {total_ms / 1000:.1f}s', flush=True)

    report = {
        'steps': len(steps),
        'dimensions': dimensions,
        'covered_sites': covered,
        'executor_sites': executor_sites,
        'registry_sites': registry_sites,
        'injected_sites': injected,
        'missed_sites': missed,
        'detected_all': detected_all,
        'total_ms': total_ms,
        'records': records,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_ROOT / time.strftime('drill_%Y%m%d_%H%M%S.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'报告: {path}', flush=True)

    return detected_all and not failed


# ═══════════════════════════════════════════════════════════════════════════════
# 探测轮: 只检测, 不注入
# ═══════════════════════════════════════════════════════════════════════════════


def _run_detect(
    rt: Any,
    navigator: Any,
    probe: _InterruptProbe,
    page_name: Any,
    steps: tuple[tuple[str, dict[str, Any]], ...],
    session: Any,
) -> dict[str, Any]:
    """不注入信号走一遍链路, 收集断点落在哪些位置。"""
    probe.arm(None, None)
    sites: list[str] = []
    failures: list[str] = []

    for index, (name, params) in enumerate(steps, start=1):
        try:
            navigator.navigate_to(page_name[name], **params)
            sites.extend(probe.take_sites())
            print(f'PASS [detect {index}/{len(steps)}] -> {name}', flush=True)
        except Exception as exc:
            failures.append(f'{name}: {type(exc).__name__}: {exc}')
            print(f'FAIL [detect {index}/{len(steps)}] -> {name}: {exc}', flush=True)
            break

    # 回退断点独有一条路径: 链路上全是 navigate_to, 回退要单独退一步再回来。
    try:
        navigator.navigate_back()
        sites.extend(probe.take_sites())
        navigator.navigate_to(page_name.HOME)
        sites.extend(probe.take_sites())
    except Exception as exc:
        failures.append(f'回退: {type(exc).__name__}: {exc}')
        print(f'FAIL [detect back] {exc}', flush=True)

    probe.disarm()
    if not failures:
        rt.check('探测轮后回到主页', lambda: session.current_page() == page_name.HOME.value)

    return {'name': 'detect', 'ok': not failures, 'sites': sites, 'failures': failures}


# ═══════════════════════════════════════════════════════════════════════════════
# 三个维度: 逐位置注入
# ═══════════════════════════════════════════════════════════════════════════════


def _fire(
    rt: Any,
    probe: _InterruptProbe,
    *,
    kind: str,
    site: str | None,
    forward_target: Any = None,
    forward_params: dict[str, Any] | None = None,
    run_back: bool = False,
) -> tuple[str, bool]:
    """走一步并尝试在 site 注入; 返回 (结局, 是否真的打断过)。"""
    from autowsgr.application.signals import TaskPaused, TaskStopped

    probe.arm(kind, site)
    outcome = 'reached'
    try:
        _make_executor(
            rt,
            target=None if run_back else forward_target,
            params=forward_params,
        ).run()
    except TaskStopped:
        outcome = 'stopped'
    except TaskPaused:
        outcome = 'paused'
    probe.disarm()
    return outcome, probe.fired


def _attempt(
    rt: Any,
    probe: _InterruptProbe,
    session: Any,
    *,
    kind: str,
    site: str | None,
    dimension: str,
    step: int,
    page: str,
    home_value: str,
    forward_target: Any,
    forward_params: dict[str, Any] | None = None,
    mode: str = 'forward',
) -> dict[str, Any]:
    """在一步上打断一次, 并按维度验证恢复语义。"""
    signals = rt.interrupt
    outcome, fired = _fire(
        rt,
        probe,
        kind=kind,
        site=site,
        forward_target=forward_target,
        forward_params=forward_params,
        run_back=mode == 'backward',
    )
    record: dict[str, Any] = {
        'dimension': dimension,
        'step': step,
        'page': page,
        'site': site,
        'mode': mode,
        'outcome': outcome,
        'fired': fired,
        'sites': probe.take_sites(),
        'ok': True,
    }
    if not fired:
        # 这一步的路径不经过该位置: 不算失败, 记下来供报告核对偏斜。
        record['skipped'] = True
        return record

    if outcome == 'stopped':
        signals.stop.clear()
        record['stack'] = session.current_page()
        # 终止的唯一正确收尾: 执行器已清栈, 并且把游戏带回了主页。
        record['ok'] = session.current_page() == home_value
        record['error'] = None if record['ok'] else '终止后没有停在主页'
        return record

    if outcome != 'paused':
        record['ok'] = False
        record['error'] = '注入点触发了但导航没有让路'
        return record

    signals.pause.clear()
    record['stack'] = session.current_page()
    if dimension == 'restart':
        # 用户暂停: 处理器清栈, 恢复时按实时识别重建 (见 dispatch.processor)。
        session.clear_pages()
    record['stack_kept'] = session.current_page()
    # 暂停重启会清栈, 回退本身已无栈可用; 恢复一律从实时识别重建后重新导航。
    resume_back = mode == 'backward' and dimension != 'restart'
    try:
        _make_executor(
            rt,
            target=None if resume_back else forward_target,
            params=forward_params,
        ).run()
        if resume_back:
            # 回退打断后没有「目标页」可比, 只要求能继续走完。
            record['ok'] = True
        else:
            record['ok'] = session.current_page() == forward_target.value
            if not record['ok']:
                record['error'] = f'恢复后停在 {session.current_page()!r}'
    except Exception as exc:
        record['ok'] = False
        record['error'] = f'恢复失败: {type(exc).__name__}: {exc}'
    return record


def _run_dimension(
    rt: Any,
    probe: _InterruptProbe,
    page_name: Any,
    session: Any,
    steps: tuple[tuple[str, dict[str, Any]], ...],
    dimension: str,
    known_sites: list[str],
) -> dict[str, Any]:
    """把链路的每一步都打断, 直到每一个已知断点位置都被真正触发过。"""
    kind = 'stop' if dimension == 'stop' else 'pause'
    pending = list(known_sites)
    records: list[dict[str, Any]] = []

    for index, (name, params) in enumerate(steps, start=1):
        target = page_name[name]
        site = pending[0] if pending else None
        record = _attempt(
            rt,
            probe,
            session,
            kind=kind,
            site=site,
            dimension=dimension,
            step=index,
            page=name,
            home_value=page_name.HOME.value,
            forward_target=target,
            forward_params=params,
        )
        records.append(record)
        if record['fired'] and site in pending:
            pending.remove(site)

        # 回退断点只出现在 navigate_back 上, 位置迟迟没被触发就补一次回退。
        if site in pending and session.current_page() not in (None, page_name.HOME.value):
            back = _attempt(
                rt,
                probe,
                session,
                kind=kind,
                site=site,
                dimension=dimension,
                step=index,
                page=name,
                home_value=page_name.HOME.value,
                forward_target=target,
                mode='backward',
            )
            records.append(back)
            if back['fired'] and site in pending:
                pending.remove(site)

        mark = 'PASS' if record['ok'] else 'FAIL'
        extra = ' (跳过: 本步不经过该位置)' if record.get('skipped') else ''
        print(
            f'[{mark}] [{dimension} {index}/{len(steps)}] {name} '
            f'site={site} outcome={record["outcome"]}{extra}',
            flush=True,
        )

    failed = [item for item in records if not item['ok']]
    print(flush=True)
    print(f'  {dimension}: {len(records)} 次打断, 失败 {len(failed)}', flush=True)
    if pending:
        print(f'  {dimension}: 仍未触发的位置 {pending}', flush=True)
    return {
        'name': dimension,
        'ok': not failed,
        'records': records,
        'attempts': records,
        'sites': [site for item in records for site in item['sites']],
    }
