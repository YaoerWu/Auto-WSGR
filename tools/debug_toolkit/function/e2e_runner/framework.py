"""E2E 快速实机验证框架 — 基座 (E2ERunner)。

算法说明:
1. 目标: 把 "连接设备 → 准备任务上下文 → 执行操作 → 判定结果" 的重复劳动收敛成
   一个基座, 验证脚本 (case) 只写业务步骤本身, 实现 "加一个文件 = 多一个可跑的
   实机验证"。
2. 初始化: `--no-launch` 用 common.device 的 DeviceService 连接设备, 并绑定
   dispatch ContextHandle 交给 case (rt.ctx); 完整模式 (启动游戏并回到首页) 依赖
   navigation.goto_page 和 application.runtime.initialize 迁移到新栈, 尚未接通。
3. 步骤执行: rt.action(label, fn) 执行任意函数并计时; 正常时原样返回 fn 的返回
   值, 抛异常时记为失败、自动截图存证并返回 FAILED 哨兵, case 据此短路退出。
4. 断言: rt.check(label, fn) 把返回值当 bool 判定, 用于次数 / 状态核对。
5. 汇总: finalize(overall) 汇总所有步骤的通过 / 失败, 结合 case 整体返回值
   给出进程退出码 (0 = 全部通过), 供终端与 CI 直接判断。
"""

from __future__ import annotations

# 处理 Windows GBK 编码兼容性 (中文输出在默认代码页下可能乱码)
import sys
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:  # noqa: S110
    pass  # reconfigure 不可用时继续使用默认编码


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════════


def _load_frame(path: str | Path) -> Any:
    """把一张外挂截图读进内存（BGR 转 RGB）。

    Args:
        path: 截图路径，允许位于仓库之外。

    Returns:
        RGB 图像数组。

    Raises:
        FileNotFoundError: 截图无法读取或解码。
    """
    # 外挂截图必须用 cv2 直接读；仓库的文件读取接口只允许仓库内路径。
    import cv2
    import numpy

    frame = cv2.imdecode(numpy.fromfile(str(path), dtype=numpy.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise FileNotFoundError(f'静态截图无法读取: {path}')
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


class _StaticFrameDevice:
    """静态截图设备替身：按调用方选定的截图返回画面。"""

    def __init__(self) -> None:
        self._frame: Any = None

    def use_frame(self, path: str | Path) -> None:
        """切换当前帧。

        Args:
            path: 外挂截图路径，允许位于仓库之外。

        Raises:
            FileNotFoundError: 截图无法读取或解码。
        """
        self._frame = _load_frame(path)

    def screenshot(self) -> Any:
        """返回当前帧。

        Raises:
            RuntimeError: 尚未选定任何截图。
        """
        if self._frame is None:
            raise RuntimeError('静态帧尚未设置')
        return self._frame

    def disconnect(self) -> None:
        """静态替身不持有设备资源。"""


class _ScriptedFrameDevice:
    """脚本化静态帧设备（混合模式）。

    前 ``static_clicks`` 次点击只记录、不落到设备上，并按 ``interval_seconds`` 把画面
    推进到脚本的下一张；脚本用完后，截图与点击都交回真机。未被覆盖的方法转发真机。

    Attributes:
        clicks: 静态阶段收到的点击坐标，供 case 核对点击内容。
    """

    def __init__(
        self,
        real: Any,
        frames: list[str | Path],
        *,
        interval_seconds: float = 1.5,
        static_clicks: int = 0,
    ) -> None:
        self._real = real
        self._frames = [_load_frame(path) for path in frames]
        self._interval_seconds = interval_seconds
        self._remaining_static_clicks = static_clicks
        self._index = 0
        self._pending_at: float | None = None
        self._live = False
        self.clicks: list[tuple[float, float]] = []

    def screenshot(self) -> Any:
        """返回当前帧；距上次点击已满推进间隔就换到脚本的下一张。"""
        if self._live:
            return self._real.screenshot()
        # 只做一次时间比较：到点就换帧，不 sleep、不阻塞调用方。
        if (
            self._pending_at is not None
            and time.monotonic() - self._pending_at >= self._interval_seconds
        ):
            self._index = min(self._index + 1, len(self._frames) - 1)
            self._pending_at = None
        return self._frames[self._index]

    def click(self, x: float, y: float, *, delay: bool = False) -> None:
        """静态阶段只记录点击并起推进计时；脚本用完后点击真的落到设备上。"""
        if self._live:
            self._real.click(x, y, delay=delay)
            return
        self.clicks.append((x, y))
        self._remaining_static_clicks -= 1
        self._pending_at = time.monotonic()
        if self._remaining_static_clicks <= 0:
            self._live = True

    def disconnect(self) -> None:
        """无论脚本是否用完，都断开真机。"""
        self._real.disconnect()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


# ── E2E 替身配置 ────────────────────────────────────────────────────────────

# autowsgr.config 仍在迁移（依赖已删除的模拟器检测与操作延迟 API），而实机链路只需要
# 账号包名与区服设置，因此这里用最小替身，不让坏掉的配置模块挡住 E2E。
# TODO: 生产配置模块迁移完成后删除本替身，改回 autowsgr.config 的 UserConfig。


@dataclass(frozen=True)
class _E2EAccount:
    """E2E 替身配置的账号段。"""

    package_name: str
    game_server: Any


@dataclass(frozen=True)
class _E2EConfig:
    """E2E 替身配置，只提供实机链路读取的账号事实。"""

    account: _E2EAccount


@dataclass
class StepRec:
    """单条步骤记录 (action / check 各记一条)。"""

    label: str  # 步骤描述 (中文, 显示给用户)
    ok: bool  # 是否通过 (action: 是否抛异常; check: 断言结果)
    duration_ms: int = 0  # 耗时 (毫秒)
    error: str | None = None  # 异常信息 (失败时)


@dataclass
class RunnerState:
    """E2ERunner 的步骤累计状态。"""

    steps: list[StepRec] = field(default_factory=list)

    @property
    def failed(self) -> int:
        """失败步骤数。"""
        return sum(1 for s in self.steps if not s.ok)


# ═══════════════════════════════════════════════════════════════════════════════
# 基座
# ═══════════════════════════════════════════════════════════════════════════════


class E2ERunner:
    """单个 E2E case 的执行基座。

    职责: 设备连接、任务上下文、步骤计时与记录、失败截图、汇总与退出码。
    case 只需调用 :meth:`action` / :meth:`check` / :meth:`note` 组织自己的步骤,
    并从 rt.ctx 拿到已绑定 runtime 的 dispatch ContextHandle。
    """

    # 失败哨兵: action 抛异常时返回它 (区别于业务返回值 None/False/空列表)
    FAILED = object()

    def __init__(
        self,
        case_name: str,
        case_args: Any,
        *,
        serial: str | None = None,
        config_path: str | None = None,
        debug: bool = False,
        no_launch: bool = False,
        static_frames: bool = False,
        with_ocr: bool = False,
        event_type: str | None = None,
        event_stage: str | None = None,
        game_server: str = '默认',
        scripted_frames: list[str | Path] | None = None,
        frame_interval_seconds: float = 1.5,
        static_clicks: int = 0,
    ) -> None:
        self.case_name = case_name
        self.args = case_args  # case 自己的参数 namespace (run.py 解析后传入)
        self.serial = serial  # ADB 序列号; None 时用 usersettings.yaml 配置
        self.config_path = config_path  # 配置文件路径; None 时自动检测
        self.debug = debug  # True 时日志级别 DEBUG
        self.no_launch = no_launch  # True 时跳过游戏就绪 (纯只读验证)
        self.static_frames = static_frames  # True 时用外挂截图离线验证 (不连接设备)
        self.with_ocr = with_ocr  # True 时初始化 OCR 引擎 (编队识别等需要)
        self.event_type = event_type  # 任务上下文的活动玩法标识 (如 stage_push)
        self.event_stage = event_stage  # 任务上下文的活动章节标识 (如 EX7)
        self.game_server = game_server  # 换区目标，取值同 LoginServer
        self.scripted_frames = scripted_frames or []  # 脚本化静态帧路径（混合模式）
        self.frame_interval_seconds = frame_interval_seconds  # 静态帧推进间隔
        self.static_clicks = static_clicks  # 前几次点击只记录不落地
        self.state = RunnerState()
        self.ctx: Any = None  # 已绑定的 dispatch ContextHandle (prepare() 成功后可用)
        self.interrupt: Any = None  # 断点开关 (prepare() 成功后可用; 默认不置位)
        self._runtime: Any = None  # RuntimeBindings: 设备、配置和 OCR 服务引用
        self._scope_stack: Any = None  # ExitStack: 持有本次运行的任务上下文作用域
        self._launcher: Any = None  # 已连接的设备服务
        self._cleanup_done = False
        # 每次运行独立目录: logs/e2e_tools/<case>/<时间戳>
        stamp = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
        self.log_dir = Path('logs/e2e_tools') / case_name / stamp

    # ── 初始化 ─────────────────────────────────────────────────────

    def prepare(self) -> bool:
        """连接设备并准备本次运行的任务上下文。

        ``no_launch=True`` 只连接设备并绑定 dispatch Context, 供截图、页面识别和
        checker 验证使用。完整模式在此基础上调用 ``dispatch.startup.ensure_ready``,
        把游戏带到首页并清掉浮层。
        """
        if self.static_frames:
            return self._prepare_static_frames()
        if self.no_launch:
            return self._prepare_readonly()
        return self._prepare_full()

    def _prepare_full(self) -> bool:
        """连接设备、绑定带替身配置的上下文, 并把游戏带到首页。"""
        from autowsgr.application.runtime.types import GameAPP, LoginServer
        from autowsgr.dispatch.startup import ensure_ready

        config = _E2EConfig(
            account=_E2EAccount(
                package_name=GameAPP.official.package_name,
                game_server=LoginServer(self.game_server),
            ),
        )
        if not self._prepare_readonly(config=config):
            return False
        return self.action('游戏就绪 (启动 → 首页)', ensure_ready, self.ctx) is not self.FAILED

    def _prepare_readonly(self, *, config: Any = None) -> bool:
        """连接设备并绑定 dispatch 任务上下文 (不启动游戏、不执行页面操作)。

        Args:
            config: 运行时配置引用; 只读运行没有生产配置可注入。
        """
        from autowsgr.common.device.config import DeviceConfig
        from autowsgr.common.device.service import DeviceService

        self._launcher = DeviceService(
            DeviceConfig(ADB_CONNECTION=self.serial) if self.serial else DeviceConfig(),
        )
        try:
            info = self._launcher.connect()
        except Exception as exc:
            self._record('连接设备', ok=False, error=str(exc))
            print(f'  [FAIL] 设备连接失败: {exc}')
            return False

        # 多显示器模拟器把应用放在非默认屏上，scrcpy 默认只镜像 0 号屏，
        # 不跟随就只能截到桌面；完整启动流程里由 startup 调用，这里补上同一步。
        self._follow_application_display(config)

        # 脚本化静态帧：先用外挂截图跑前几步（点击不落地），之后交回真机。
        ctrl: Any = self._launcher
        if self.scripted_frames:
            ctrl = _ScriptedFrameDevice(
                self._launcher,
                self.scripted_frames,
                interval_seconds=self.frame_interval_seconds,
                static_clicks=self.static_clicks,
            )
            self.note(
                f'脚本化静态帧: {len(self.scripted_frames)} 张，'
                f'前 {self.static_clicks} 次点击不落地，间隔 {self.frame_interval_seconds} 秒',
            )

        # OCR 引擎仍在迁移中; 需要配置的完整实机链路由 _prepare_full 传入替身配置。
        self._bind_task_context(ctrl, config=config)
        if self.with_ocr:
            self.note('只读模式不初始化 OCR: 新栈 OCR 入口迁移中, 该参数当前被忽略')
        print(f'  [OK] 设备已连接: {info.serial} {info.resolution[0]}x{info.resolution[1]}')
        return True

    def _follow_application_display(self, config: Any = None) -> None:
        """让截图目标跟随游戏所在的显示器 (只读模式跳过启动流程，需要手动补)。"""
        from autowsgr.application.runtime.types import GameAPP

        package = getattr(getattr(config, 'account', None), 'package_name', None)
        if not package:
            package = GameAPP.official.package_name
        try:
            self._launcher.follow_display(package)
        except Exception as exc:
            self.note(f'显示器跟随失败: {exc}')

    def _prepare_static_frames(self) -> bool:
        """用静态截图替身准备离线验证 (不连接设备、不启动游戏)。"""
        self._launcher = _StaticFrameDevice()
        self._bind_task_context(self._launcher)
        print('  [OK] 静态帧模式: 使用外挂截图, 不连接设备')
        return True

    def _bind_task_context(self, ctrl: Any, *, config: Any = None) -> None:
        """绑定本次运行的 dispatch 任务上下文。

        Args:
            ctrl: 已就绪的运行时设备引用。
            config: 运行时配置引用; 只读运行没有配置可注入。
        """
        from autowsgr.dispatch.context import (
            ContextTemplate,
            InterruptSignals,
            RuntimeBindings,
            context,
        )

        # OCR 引擎仍在迁移中; 只读运行也只消费设备引用。
        self._runtime = RuntimeBindings(ctrl=ctrl, config=config, ocr=None, ship_ocr=None)
        # 断点开关: 默认两个都不置位, 对不碰断点的 case 完全透明;
        # 断点演练 case 自己 set/clear, 模拟处理器发出的暂停与终止。
        self.interrupt = InterruptSignals(pause=threading.Event(), stop=threading.Event())
        self._scope_stack = ExitStack()
        self._scope_stack.enter_context(
            context.bind(
                f'e2e:{self.case_name}',
                template=ContextTemplate.for_task(
                    'navigation_checker',
                    event_type=self.event_type,
                    event_stage=self.event_stage,
                ),
                runtime=self._runtime,
                interrupt=self.interrupt,
            ),
        )
        self.ctx = context.request()

    # ── 步骤 API (case 调用) ───────────────────────────────────────

    def use_frame(self, path: str | Path) -> None:
        """切换静态验证使用的截图。

        Args:
            path: 外挂截图路径; 换机器或换活动时由 case 指定。

        Raises:
            RuntimeError: 当前不是静态帧模式。
        """
        if not isinstance(self._launcher, _StaticFrameDevice):
            raise TypeError('只有静态帧模式可以切换截图')
        self._launcher.use_frame(path)

    def action(self, label: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        """执行一个操作步骤。

        正常返回 fn 的返回值; 抛异常时记录失败、自动截图、返回 ``rt.FAILED``。
        case 约定写法::

            results = rt.action('跑常规战', run_normal_fight_from_yaml, ctx, '1-1')
            if results is rt.FAILED:
                return False
        """
        t0 = time.monotonic()
        try:
            value = fn(*args, **kwargs)
        except Exception as exc:
            self._record(label, ok=False, error=str(exc), t0=t0)
            print(f'  [FAIL] {label}: {exc}')
            self._error_screenshot(label)
            return self.FAILED
        self._record(label, ok=True, t0=t0)
        print(f'  [OK] {label} ({self._ms_since(t0)}ms)')
        return value

    def check(self, label: str, fn: Any, /, *args: Any, **kwargs: Any) -> bool:
        """断言步骤: 把 fn 返回值当 bool 判定, 打印 PASS/FAIL。"""
        t0 = time.monotonic()
        try:
            passed = bool(fn(*args, **kwargs))
            error: str | None = None
        except Exception as exc:
            passed = False
            error = str(exc)
        self._record(label, ok=passed, error=error, t0=t0)
        mark = 'PASS' if passed else 'FAIL'
        suffix = f': {error}' if error else ''
        print(f'  [{mark}] {label}{suffix}')
        return passed

    def note(self, msg: str) -> None:
        """打印一条说明信息 (不计入步骤, 不影响判定)。"""
        print(f'  [i] {msg}')

    # ── 兜底与汇总 ─────────────────────────────────────────────────

    def unexpected(self, exc: Exception) -> None:
        """case 主体自身抛出的未捕获异常兜底 (记为一条失败步骤)。"""
        self._record(f'case 异常 ({type(exc).__name__})', ok=False, error=str(exc))
        print(f'  [FAIL] case 异常: {exc}')
        self._error_screenshot('case_crash')

    def finalize(self, *, overall: bool = True) -> int:
        """先释放运行资源，再打印汇总并返回进程退出码。"""
        self.cleanup()
        total = len(self.state.steps)
        failed = self.state.failed
        print()
        print('═' * 68)
        for i, s in enumerate(self.state.steps, 1):
            mark = 'OK  ' if s.ok else 'FAIL'
            dur = f'{s.duration_ms}ms' if s.duration_ms else ''
            err = f'  ← {s.error}' if s.error else ''
            print(f'  [{mark}] [{i:02d}] {s.label}  {dur}{err}')
        verdict = 'PASS' if (failed == 0 and overall) else 'FAIL'
        print()
        print(f'  {self.case_name}: {total} 步, 失败 {failed} 步 → {verdict}')
        print(f'  日志目录: {self.log_dir.resolve()}')
        print('═' * 68)
        return 0 if verdict == 'PASS' else 1

    def cleanup(self) -> None:
        """无论 case 结果如何，关闭任务上下文并释放设备连接。"""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        # 先退出任务上下文作用域, 再断开设备, 避免残留绑定阻塞下一次 bind。
        if self._scope_stack is not None:
            self._scope_stack.close()
            self._scope_stack = None

        if self._launcher is None:
            return
        try:
            self._launcher.disconnect()
        except Exception as exc:
            self._record('清理: 断开设备', ok=False, error=str(exc))
            print(f'  [FAIL] 清理: 断开设备: {exc}')

    # ── 内部工具 ───────────────────────────────────────────────────

    @staticmethod
    def _ms_since(t0: float) -> int:
        return int((time.monotonic() - t0) * 1000)

    def _record(
        self,
        label: str,
        *,
        ok: bool,
        error: str | None = None,
        t0: float | None = None,
    ) -> None:
        self.state.steps.append(
            StepRec(
                label=label,
                ok=ok,
                duration_ms=self._ms_since(t0) if t0 is not None else 0,
                error=error,
            )
        )

    def _error_screenshot(self, label: str) -> None:
        """失败时自动截图存证 (截图本身失败则静默跳过)。"""
        if self._runtime is None or self._runtime.ctrl is None:
            return
        try:
            # 失败分支才需要图片工具，避免普通 runner 导入时加载图像编码依赖。
            from tools.debug_toolkit.function.screenshot import save_image

            screen = self._runtime.ctrl.screenshot()
            tag = f'e2e_fail_{label.replace(" ", "_")[:40]}'
            path = save_image(screen, tag=tag, img_dir=self.log_dir / 'images')
            if path:
                print(f'        失败截图: {path}')
        except Exception:  # noqa: S110
            pass
