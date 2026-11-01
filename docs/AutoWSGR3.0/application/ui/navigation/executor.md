# application-ui-navigation-executor 架构说明

版本：AutoWSGR-3.0 第 1 版
状态：生效
适用范围：`autowsgr/application/ui/navigation/executor.py`
实现基线：`codex/20260913-shiinaskuya-upgrade-7b3e`，2026-10-13（导航器样板去重）

## 1. 模块定位

executor 是 **application 层导航器**的路径执行器。它只做一件事：**把已经算好的路径一步步走出去**，
并在每一跳的两端自动做前后识别。

它明确不负责：算路（属于 [registry](<./registry.md>)）、入口编排与启动段（属于 `service.py`）、
点击落点与坐标（属于 UI 控制器）、画面识别规则（属于 [checker](<./checker.md>)）。

所有权：

- 执行器只持有调用方注入的 `ContextHandle` 与进程级导航栈（`dispatch.session` 的 `SessionState`）；
- 路径与参数由调用方传入，执行器不缓存路径；
- 本模块没有配置、没有独立错误类型，失败一律抛 `NavigationError`。

## 2. 模块架构

### 2.1 文件形态

~~~text
autowsgr/application/ui/navigation/
└── executor.py      # 逐边执行 + 前后识别
~~~

### 2.2 文件内部结构

| 分区 | 内容 |
| --- | --- |
| 页面内标签参数 | `_TAB_SETTLE_SECONDS`、`_TAB_CLICK_ATTEMPTS`、`_TAB_RETRY_INTERVAL_SECONDS` |
| 两个方向 | `walk_forward`、`walk_backward` |
| 断点 | `_check_interrupt` |
| 页面层识别 | `detect_layer`、`_enter_tab`、`_confirm_arrival` |

文件顶部共有七个模块级常量，都是流程时序、不是配置，取值见 [§10](#10-统一配置)。

### 2.3 依赖方向

~~~text
service
   ↓
NavigationExecutor（本模块）
   ↓
registry（取确认入口与深度） + types（页面名与错误）
   ↓
dispatch.session（导航栈）
~~~

禁止方向：

- executor 不导入 `service.py`（service 导入 executor，反向会循环）；
- executor 不直接调用 checker 或控制器，只通过 [registry](<./registry.md>) 取入口；
- executor 不算路、不判断入口、不处理业务状态。

### 2.4 出口策略

唯一稳定出口是 `NavigationExecutor`；`_check_interrupt`、`_enter_tab`、`_confirm_arrival` 与全部模块级常量都是内部实现。

## 3. 能力总览

| 能力 | 对外入口 | 输入 | 输出/副作用 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- | --- | --- |
| 前进执行 | `NavigationExecutor.walk_forward` | 路径、参数 | 点击、确认、记栈 | 逐边执行并确认到达 | 算路、栈的起点判断 |
| 后退执行 | `NavigationExecutor.walk_backward` | 路径 | 点击、确认 | 逐边回退并确认到达 | 弹栈记账 |
| 当前层识别 | `NavigationExecutor.detect_layer` | `attempts`、`interval_seconds` | 返回 `tuple[PageName, ...]` | 域探针 + 逐页确认，按深度降序 | 等待页面切换、处理识别失败 |

## 4. 前进执行：walk_forward

### 4.1 能力说明

从当前页沿路径走到目标页。每一跳依次执行：边的动作 → 到达确认（或标签确认）→ 记栈。
一次点击的语义天然成对：旧页面的标志应当消失、新页面的标志应当出现，这个判断由执行器统一负责。

### 4.2 稳定入口

~~~text
NavigationExecutor.walk_forward(path: tuple[NavTarget, ...], params: dict[str, object]) -> None
~~~

- `path`：由 [registry](<./registry.md>).find_path 算出的边序列；
- `params`：调用方经 `navigate_to` 透传的参数，原样交给每条边的 `action`；
- 副作用：执行点击、按到达确认结果记栈；失败抛 `NavigationError`。

### 4.3 标签的选择顺序

1. 调用方显式给的 `params['tab']` 只落在**最后一跳**：走到目的地再切，中途切了还得切回来；
2. 其余每一跳用边自己声明的 `tab`（如「首页 → 演习页」固定切演习）。多跳路径里
   中间那一跳同样要切——不切的话后面那跳的到达确认会认成默认标签页，直接报错；
3. 这一跳既没有调用方标签、也没有边标签时，走页面级到达确认。

### 4.4 调用示例

~~~python
from autowsgr.application.ui.navigation.executor import NavigationExecutor
from autowsgr.application.ui.navigation.types import PageName
from autowsgr.application.ui.navigation import registry

path = registry.find_path(PageName.HOME, PageName.SORTIE_MAP)
NavigationExecutor(ctx, session).walk_forward(path, {'tab': 'sortie'})
~~~

### 4.5 错误和副作用

| 场景 | 行为 | 异常/结果 | 处理者 |
| --- | --- | --- | --- |
| 到达确认失败 | 停止执行 | `NavigationError` | `service.py` / dispatch |
| 标签不存在 | 停止执行 | `NavigationError` | 调用方修正参数 |
| 标签未激活 | 停止执行 | `NavigationError` | 调用方修正参数 |

### 4.6 记栈：压 / 换 / 不动

每一跳确认到达后，执行器按四条规则记账（内部实现 `_record_page`）：

| 情形 | 记账 | 理由 |
| --- | --- | --- |
| 目标是浮窗（`registry.is_overlay_page`） | 不动 | 浮窗只是页面里的一层覆盖，不是独立页面 |
| 目标和栈顶是同一个页面 | 不动 | 关掉浮窗回到原页面，位置没变 |
| 目标和栈顶同域（`registry.domain_of` 相等） | 替换栈顶 | 同一套画面框架里换标签页，旧标签已经不在画面上 |
| 跨域，或栈顶根本不在任何域里 | 压一格 | 真的换了一层画面，回退要退到这里 |

栈空时一律压一格。四条规则合起来，「首页 → 演习页 → 对手浮窗 → 演习准备页」
记成 `[首页, 演习页, 演习准备页]`：浮窗不占格，所以从准备页 `navigate_back`
直接弹回演习页，不会弹到已经被挑战按钮消费掉的浮窗上。

记栈只看两个页面的域，不看「这一步是不是 go_back」：同一条准备页 → 演习页的边，
前进走和回退走记出来的栈一致，调用方不必关心自己走的是哪个方向。

## 5. 后退执行：walk_backward

### 5.1 能力说明

按路径从当前页退回上一页。与前进只有两点差别：**不接受调用方参数**；**不动栈**——
弹栈记账由 `service.py` 的 `navigate_back` 完成，这里只走路径、点、确认。

### 5.2 稳定入口

~~~text
NavigationExecutor.walk_backward(path: tuple[NavTarget, ...]) -> None
~~~

### 5.3 为什么不能按步数记账

回退一个「锚点」跟路径上有几步无关（中间可能经过浮窗链），因此不能用「走了几步就弹几层」记账，
必须由调用方在回退前显式弹一层。

### 5.4 错误和副作用

与前进相同：到达确认失败抛 `NavigationError`；不修改导航栈。

## 6. 断点协作：_check_interrupt

### 6.1 能力说明

执行器是导航链路上唯一知道「现在走到哪一跳」的角色，所以让路（暂停、终止、插队）的检查点
放在执行器里，不放边动作里。断点只在**边与边之间**：一条边的动作是连续动作（选章选节要连点
十几次、每次等 1.5 秒），中途让路会停在半路。

### 6.2 位置

| 位置 | 时机 | 理由 |
| --- | --- | --- |
| `walk_forward` 进入循环前 | 还没点第一下 | 重跑时一进门就能再停一次 |
| 每条边记栈之后 | 确认到达 + 记栈完成 | 回退路径完整，让路不丢位置 |
| `walk_backward` 每条边确认之后 | 回退到这一页 | 回退途中也能停 |

边动作内部只有一个例外：`registry._sortie_map_to_preparation` 在选完章、进准备页之前
自己调一次 `ctx.check_interrupt()`——那一段是连续动作，导航器看不见它内部的分界。

### 6.3 判定交给 dispatch

执行器不判断「该不该停」，只问一次 `ContextHandle.check_interrupt()`；这个入口由 dispatch
Context 提供，收到信号就抛 `TaskPaused` 或 `TaskStopped`（两者同时置位时 stop 优先）。
执行器不解析开关、不做恢复决策。

### 6.4 打断之后由谁收尾

| 信号 | 收尾方 | 动作 |
| --- | --- | --- |
| 暂停 | `dispatch.processor` | 清导航栈（用户可能改过游戏状态，栈不可信），重跑时按实时识别重建 |
| 插队 | `dispatch.processor` | 保留导航栈，高优先级任务处理完回到原任务进度 |
| 终止 | `dispatch.executor.BaseExecutor.run()` | 清栈 → 回主页 → 上报 `stopped` → 重新抛出 |

回主页那一次导航必须用 `NavigationService(..., checkpoint=False)`：停止开关还亮着，
不带这个参数会在第一条边就再次抛出，永远回不到主页。

### 6.5 为什么传开关而不是传状态

`checkpoint: bool = True` 只控制「要不要问」；开关本身是 dispatch 注入 Context 的
`threading.Event` 引用，不是快照——处理器一置位，下一个断点立刻看到，中间没有轮询间隔。
## 7. 当前层识别：detect_layer

### 7.1 能力说明

回答「我现在在哪一页」。先调 `registry.probe_domains` 让每个域一次读一帧，
再按页面深度降序扫描其余逐页注册的确认入口；合并命中后按深度降序返回。
覆盖层（浮窗、侧边栏、二级菜单）总比被盖住的页面更深，因此排在最前的命中者就是当前层。

### 7.2 稳定入口

~~~text
| 当前层识别 | `NavigationExecutor.detect_layer` | `attempts`、`interval_seconds` | 返回 `tuple[PageName, ...]` | 域探针 + 逐页确认，按深度降序 | 等待页面切换、处理识别失败 |
~~~

### 7.3 行为细节

| 细节 | 规则 |
| --- | --- |
| 扫描顺序 | `registry.depth_of` 降序；不可达页面排在最后 |
| 域探针 | 先问 `registry.probe_domains`：每个域一次读一帧（主页浮窗、出征标签+演习浮窗、四种准备页三组）；
同一帧里可能同时看到多层（浮窗叠在标签栏之上），探针把它们全部返回 |
| 每个入口的节奏 | 默认 `attempts=1, interval_seconds=0.2`，只看当前一帧；等页面切换的调用方传自己的节奏 |
| 入口抛异常 | 视为不匹配，继续下一层（活动 checker 需要任务上下文，探测时可能没有） |
| 全部未命中 | 返回空元组 `()`；调用方必须把它当异常处理，不能当成「无法判断所以放行」 |
| 扫描期间日志 | 静默 `_QUIET_DURING_PROBE` 两个通道，只由调用方留一条汇总 |

### 7.4 错误和副作用

本方法不抛异常、不改状态；它只截图识别。

## 8. 内部实现：标签切换 _enter_tab

~~~text
NavigationExecutor._enter_tab(page: PageName, tab: str) -> None
~~~

流程：查 [registry](<./registry.md>).get_tabs 取标签项 → 等 `_TAB_SETTLE_SECONDS`（2 秒）→
点标签 → 用**标签自己的 checker** 确认；没确认上就再等 `_TAB_RETRY_INTERVAL_SECONDS` 点一次，
最多 `_TAB_CLICK_ATTEMPTS`（2 次）。

为什么要重试：页面入口点下去到标签栏属于「这一页」之间有入场动画，这期间点下去会落到上一页；
目标标签已经激活时再点一次不改变状态，所以重试是安全的。

传了标签时页面级确认不参与：切到别的标签之后，认「默认标签激活」的页面级 checker 本来就该失败，
两者互斥。标签不存在或两次都没切过去都抛 `NavigationError`。

标签 checker 必须写成**严格相等**（例如 `read_sortie_layer(ctx) == (PageName.EXERCISE,)`），
不能用「包含」：演习浮窗开着时探针同时返回 `(演习对手浮窗, 演习页面)`，用包含会把
「浮窗还压在上面」误判成「标签已经切过去」。

## 9. 内部实现：到达确认 _confirm_arrival

~~~text
NavigationExecutor._confirm_arrival(edge: NavTarget) -> None
~~~

到达首页或侧边栏且三个每日浮窗标记不齐时，先等 `_ARRIVAL_SETTLE_SECONDS`（3 秒），
让延迟弹出的浮窗露出来，再做判层。

1. **目标页出现**
   - 域页面：动作刚点下去画面还在切换，先等 `_DOMAIN_ARRIVAL_SETTLE_SECONDS`（2 秒），
     再问一次域探针，取返回层里**最深的那个**（`max(layers, key=registry.depth_of)`），
     要求它严格等于目标页才算到达。域探针一帧判完整族，组内页面互斥，不再扫全层。
     为什么不能用「包含」：关浮窗那一跳若没真关掉，探针会返回
     `(演习对手浮窗, 演习页面)`，目标页在元组里，但它上面还压着浮窗，人其实没回到演习页。
     用最深一层比，这种情况直接判失败并抛错。
   - 其余页面：调用 registry.get_checker(edge.target) 的入口，入口自带轮询，负责等切换完成。
   - 边声明 `confirm=False` 或没有确认入口时直接跳过。
2. **当前层就是目标**（仅逐页页面）：再跑一次 `detect_layer`，要求返回的最上层严格等于目标页。
   目标出现不代表它就在最上面——浮窗、侧边栏这类覆盖层会盖住它。
3. **到达记账**：确认成功后调 `registry.on_arrival`，回到干净主页时写每日浮窗标记。
4. **稳定窗口**（仅逐页页面）：记账之后再等 `_ARRIVAL_REST_SECONDS`（1.2 秒）才把控制权
   交回调用方。到达只说明目标页的标志已经出现在画面里，入场动画往往还没走完；这段动画期间
   点下去会落到上一页。域页面已在第 1 步等过稳定窗口，不再重复等。

## 10. 统一配置

本模块无运行时配置。文件顶部常量是流程时序，不是配置：

| 常量 | 值 | 作用 |
| --- | --- | --- |
| `_TAB_SETTLE_SECONDS` | `2.0` | 点标签前等页面入场稳定的秒数 |
| `_TAB_CLICK_ATTEMPTS` | `2` | 标签「点击 + 确认」的总次数 |
| `_TAB_RETRY_INTERVAL_SECONDS` | `2.0` | 标签没切过去时，下一次点击前再等的秒数 |
| `_ARRIVAL_SETTLE_SECONDS` | `3.0` | 到达首页/侧边栏后等浮窗弹出的秒数 |
| `_DOMAIN_ARRIVAL_SETTLE_SECONDS` | `2.0` | 到达域页面后、问域探针前等画面稳定的秒数 |
| `_ARRIVAL_REST_SECONDS` | `1.2` | 逐页页面确认成功后到交还控制权的稳定窗口 |
| `_QUIET_DURING_PROBE` | 两个模块前缀 | 全层扫描期间静默日志的通道 |

## 11. 错误约定

| 错误 | 定义位置 | 触发条件 | 处理者 | 是否可重试 |
| --- | --- | --- | --- | --- |
| `NavigationError` | `types.py` | 到达确认失败、当前层不符、标签缺失或重试后仍未切换 | `service.py` 与 dispatch | 由上层决定（dispatch 可 SL） |
| `TaskPaused` | `application/signals.py` | 断点读到暂停或插队信号 | `dispatch.processor` | 由 dispatch 决定重新入队 |
| `TaskStopped` | `application/signals.py` | 断点读到终止信号 | `dispatch.executor.BaseExecutor.run()` | 不重试（终局） |

executor 不捕获自己抛出的错误，也不做恢复决策。

## 12. 日志约定

通道为 `ui.navigation.executor`（`get_logger('ui.navigation.executor')`）。

| 级别 | 记录内容 |
| --- | --- |
| `DEBUG` | 每跳的前进/后退边说明；到达确认的跳过、成功与标签确认成功 |
| `INFO` | 不记录（路径的开始与完成由 `service.py` 记录） |
| `WARNING` / `ERROR` | 不记录（失败以异常交给上层） |

扫描期间的识别细节日志整体静默，避免一次探测刷出上百条。

## 13. 公开出口和调用边界

### 13.1 稳定出口

| 出口 | 来源 | 调用者可以做什么 | 调用者不能做什么 |
| --- | --- | --- | --- |
| `NavigationExecutor` | `executor.py` | 构造执行器，调用三个公开方法 | 调用私有方法、改模块级常量 |

### 13.2 内部内容

`_check_interrupt`、`_enter_tab`、`_confirm_arrival`、`_TAB_SETTLE_SECONDS`、`_ARRIVAL_SETTLE_SECONDS`、`_QUIET_DURING_PROBE` 均为内部实现。
测试为替换等待行为会 monkeypatch `executor.time.sleep`，这是测试手段，不构成生产出口。

## 14. 模块维护方法

### 14.1 新增一个覆盖层页面

覆盖层页面加入对应的域探针（`registry._DOMAIN_PROBERS`），并在 [registry](<./registry.md>)
里登记边；逐页注册表只放普通页面。

### 14.2 调整标签切换等待

改 `_TAB_SETTLE_SECONDS`。等待属于流程时序，不放进 `checker.py` 的常量区（那是校准数据）。

### 14.3 新增一种到达确认分支

先在 [registry](<./registry.md>) 的 `NavTarget` 上找现成字段表达（`confirm`、`tab`），
确实表达不了才改 `_confirm_arrival`，并同步本节与 `types.py` 的字段表。

### 14.4 参数传入与穿透规则

| 参数 | 来源 | 规则 |
| --- | --- | --- |
| `path` | `service.py` 算好后传入 | 执行器只执行，不重新算 |
| `params` | 调用方经 `navigate_to` 传入 | 原样透传给每条边的 `action`，执行器不解释内容 |
| `tab` | `params` 或边的 `tab` 字段 | 只作用于最后一跳 |

### 14.5 删减能力

先 grep 确认没有调用方，再删实现与本节说明，最后跑门禁。

## 15. 验收门禁

| 检查 | 手段 |
| --- | --- |
| 公共入口 import smoke | `python -c "from autowsgr.application.ui.navigation.executor import NavigationExecutor"` |
| 静态检查 | `ruff check autowsgr/application/ui/navigation/executor.py` |
| 模块单测 | `pytest testing/application/ui/navigation` |
| 实机链路 | `python tools/debug_toolkit/main.py e2e --no-launch --event-type stage_push --event-stage EX1 nav_chain` |
| 文档与代码一致 | 本节的分支与 `_confirm_arrival` / `_enter_tab` 对齐；`git diff --check` |
