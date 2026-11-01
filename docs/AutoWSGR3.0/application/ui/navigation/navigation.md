# application-ui-navigation 架构说明

版本：AutoWSGR-3.0 第 2 版（第 1 版为 2026-10-12 的维护视角版本，本次按架构文档规范重写）
状态：生效
适用范围：`autowsgr/application/ui/navigation`
实现基线：`codex/20260913-shiinaskuya-upgrade-7b3e`，2026-10-13

## 1. 模块定位

navigation 是 **application 层**的 UI 导航器。它把「游戏现在在哪个页面」变成「走到哪个页面」，
并且每走一步都能确认走成了。

一句话划边界：**它只处理「页面到页面」**。启动画面（黑屏 / 更新 / 加载）不是页面，由启动段单独处理；
进程生死、何时 SL、是否换区由 dispatch 决定。

它明确不负责：页面坐标与校准数据、OCR 参数、业务流程、进程生死、任务恢复决策。

所有权：

- 导航栈与进程级标记由 `dispatch.session.SessionState` 持有，导航器只读写它；
- 页面确认与可达边由 [registry](<./registry.md>) 独占持有，运行期只读；
- 路径执行与逐跳确认由 [executor](<./executor.md>) 负责；
- 画面识别规则由 [checker](<./checker.md>) 负责；
- 模板加载由 [application.ui.template](<../template.md>) 负责并缓存。

## 2. 模块架构

### 2.1 目录树

~~~text
autowsgr/application/ui/navigation/
├── __init__.py      # 包入口，刻意不导出实现（避免与控制器循环导入）
├── checker/         # 各页面识别模块
├── executor.py      # 逐边执行与前后识别
├── registry.py      # 三张注册表与算路
├── service.py       # 对外入口：导航、回退、启动段
└── types.py         # 页面名、边模型与导航错误
~~~

### 2.2 文件职责

| 子项 | 文档 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- |
| `__init__.py` | 本表说明 | 包归属声明；`__all__` 为空 | 导出实现、隐式初始化 |
| `checker/` | [checker](<./checker.md>) | 各页面识别入口 | 点击、算路、流程编排 |
| `executor.py` | [executor](<./executor.md>) | 执行已算好的路径，逐跳做前后识别 | 算路、编排、启动段 |
| `registry.py` | [registry](<./registry.md>) | 页面确认表、可达边表、标签表与算路 | 识别、点击、执行 |
| `service.py` | 本文件「能力」章节 | 对外入口：`navigate_to` / `navigate_back` / `navigate_to_login` | 路径执行、识别细节 |
| `types.py` | 本表说明 | 页面名 `PageName`、`NavTarget` / `NavTab` 模型、`NavigationError` / `ManualUpdateRequiredError` | 导航逻辑、识别、点击 |

`service.py` 与 `types.py` 没有独立子文档：`types.py` 是纯数据文件，写进本表；
`service.py` 的三个入口就是本模块的对外能力，写进本文件的第 4–6 章。

### 2.3 依赖方向

~~~text
dispatch / business（调用方）
        ↓
navigation.service（对外入口）
        ↓
navigation.executor（执行） → navigation.registry（算路与确认入口） → checker（识别）
        ↓
application.ui.controller（点击落点）
        ↓
common.vision（识别算法） / dispatch.session（导航栈）
~~~

禁止方向：

- `__init__.py` 不导出实现：控制器需要 `navigation.types`，若包入口顺带加载 `service` 会形成循环导入；
- registry 不导入 service 或 executor；
- checker 不点击、不算路、不依赖 registry；
- 页面控制器不得反向导入 navigation（只允许导入 `navigation.types`）；
- dispatch 的代码里不出现任何 checker 调用（识别与点击全部由 UI 层编排）。

### 2.4 公开出口策略

稳定出口是 `service.NavigationService` 与 `types` 的公开类型；`registry` 与 `executor` 供导航器内部
与测试使用；`checker` 只通过各子包入口被 registry 引用。

## 3. 能力总览

| 能力 | 对外入口 | 所在文件 | 输入 | 输出/副作用 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- | --- | --- | --- |
| 导航到目标页面 | `NavigationService.navigate_to` | `service.py` | 目标页、透传参数 | 点击、确认、记栈 | 算路并执行 | 业务动作、恢复决策 |
| 回退上一页 | `NavigationService.navigate_back` | `service.py` | 无 | 弹栈、点击、确认 | 按栈回退一层 | 跨多层回退 |
| 启动段 | `NavigationService.navigate_to_login` | `service.py` | 无 | 识别启动信号 | 把游戏带到登录页 | 拉起进程、换区 |
| 断点让路 | 无（执行器内部调 `ContextHandle.check_interrupt`） | `executor.py` | 无 | 抛 `TaskPaused` / `TaskStopped` | 每跳确认到达并记栈之后问一次 dispatch | 判断该不该停、打断后的收尾 |

模块当前规模：**31 个已接入页面（14 个由域探针一帧判族、17 个逐页登记）、55 条可达边、3 个页面共 8 个标签、3 个域探针**；
`PageName` 共 33 个成员，其余 2 个是尚未接入导航图的预留页面（军阶室技能列表、选择舰船）。
对未接入页面调用 `navigate_to` 会抛「没有可达路径」，这是预期行为。

## 4. 导航到目标页面：navigate_to

### 4.1 能力说明

把游戏从当前页带到目标页。当前页优先取导航栈顶；栈空时遍历全部确认入口识别一帧再建栈。

### 4.2 稳定入口

~~~text
NavigationService.navigate_to(target: PageName, **params: object) -> None
~~~

- `target`：目标页面；
- `**params`：透传给边动作的参数（例如活动章节的 `stage`、区服的 `server`、页面标签的 `tab`）；
- 副作用：执行点击、按确认结果记栈；起点即目标时直接返回（只记一条 INFO 日志）。

### 4.3 调用示例

~~~python
from autowsgr.application.ui.navigation.service import NavigationService
from autowsgr.application.ui.navigation.types import PageName

navigator = NavigationService(ctx)
navigator.navigate_to(PageName.HOME)
navigator.navigate_to(PageName.SORTIE_MAP, tab='exercise')
navigator.navigate_to(PageName.LOGIN_PAGE, server='昆西')
~~~

### 4.4 一次调用怎么跑

~~~text
navigate_to(target, **params)
  ① _current_page()   栈顶有就用栈顶；栈空则按页面深度遍历全部 checker 认出当前页
  ② 起点即目标        → 短路返回
  ③ registry.find_path()  BFS 在可达表上找最短路径；到不了抛 NavigationError
  ④ executor.walk_forward()  逐边执行：边的动作 → 到达确认（或标签确认）→ 记栈 → 过断点
~~~

### 4.5 导航栈怎么记

栈里一格是**一个页面**，不是一次点击。四条规则合起来决定每一跳记什么：

| 情形 | 记账 | 理由 |
| --- | --- | --- |
| 目标是浮窗（`registry.is_overlay_page`） | 不动 | 浮窗只是页面里的一层覆盖，关掉就回到原页面 |
| 目标和栈顶是同一个页面 | 不动 | 画面没变 |
| 目标和栈顶同域（`registry.domain_of` 相等） | 替换栈顶 | 同一套画面框架里换标签，旧标签已经不在画面上 |
| 跨域 | 压一格 | 真的换了一层画面，回退要退到这里 |

所以「首页 → 演习页 → 对手浮窗 → 演习准备页」记成 `[首页, 演习页, 演习准备页]`：
浮窗不占格，演习页和出征页同域所以互相替换。从准备页 `navigate_back` 弹一格回到演习页，
正是画面实际回到的那一页——浮窗那层根本没进栈，不会弹到一个已经被挑战按钮消费掉的页面上。

栈空时（冷启动）先扫一帧再建栈：扫到的浮窗（`_OVERLAY_PAGES`）先关掉，栈落在它下面那层。
公告浮窗把主页模板整个挡住、扫不出下面那层时，兜底 `PageName.HOME`。

### 4.6 错误和副作用

| 场景 | 行为 | 异常/结果 | 处理者 |
| --- | --- | --- | --- |
| 栈空且认不出当前页 | 停止 | `NavigationError` | dispatch（可 SL） |
| 没有可达路径 | 停止 | `NavigationError` | 调用方修正目标或补边 |
| 到达确认失败 | 停止 | `NavigationError` | dispatch（可 SL） |
| 断点收到暂停或插队 | 停止，栈清不清由 dispatch 决定 | `TaskPaused` | `dispatch.processor` |
| 断点收到终止 | 停止 | `TaskStopped` | `dispatch.executor.BaseExecutor.run()`（清栈 → 回主页） |

## 5. 回退上一页：navigate_back

### 5.1 能力说明

回到导航栈里的上一个页面。栈为空时直接抛错，不识别当前页。

### 5.2 稳定入口

~~~text
NavigationService.navigate_back() -> None
~~~

### 5.3 记账规则

`navigate_back` 先弹一层栈，再用 `registry.find_path(current, previous)` 算回退路径交给
[executor](<./executor.md>) 的 `walk_backward`；执行器不再动栈。
回退一个「锚点」跟路径上有几步无关，因此不能按步数记账。

## 6. 启动段：navigate_to_login

### 6.1 能力说明

把处于启动阶段的游戏带到「登录页」。启动三信号由游戏特性决定：

| 信号 | 处理 |
| --- | --- |
| 健康游戏提示（黑屏） | 宽泛校验：识别不到就等一会儿再看下一项 |
| 更新提示 | 唯一硬分支：弹出即抛 `ManualUpdateRequiredError`，交人工处理 |
| 加载中 | 宽泛校验：没在加载就往下走 |

调用方负责在游戏没运行时拉起 App；本方法不碰进程，也不做换区。

### 6.2 稳定入口

~~~text
NavigationService.navigate_to_login() -> None
~~~

### 6.3 流程参数

| 常量 | 值 | 作用 |
| --- | --- | --- |
| `_STARTUP_STEP_WAIT_SECONDS` | `3.0` | 宽泛校验不成立时的等待秒数 |
| `_PROBE_ATTEMPTS` | `3` | 确认画面消失、读取更新提示与加载状态的探测次数 |
| `_LOGIN_PAGE_ATTEMPTS` | `60` | 等登录页出现的最大识别次数 |
| `_STARTUP_INTERVAL_SECONDS` | `1.0` | 相邻两次识别的间隔秒数 |

### 6.4 错误和副作用

| 场景 | 行为 | 异常/结果 | 处理者 |
| --- | --- | --- | --- |
| 检测到游戏更新 | 停止 | `ManualUpdateRequiredError` | dispatch 转成人工处理 |
| 启动超时 | 停止 | `NavigationError` | dispatch（可 SL） |

## 7. 当前页识别（service 内部）

`_current_page` 是 `service.py` 的私有实现：栈顶有页面就直接用；栈空时调
[executor](<./executor.md>).detect_layer 按页面深度扫一遍；扫到的第一层是浮窗就先关掉它，
栈记在它下面那层（扫不到下面那层时兜底主页）。
扫描期间识别细节日志整体静默，结束后只留一条汇总（耗时 + 结果）。

## 8. 统一配置

本模块无运行时配置。第 6 章的四个常量是启动段流程参数，不是配置；
识别节奏属于各 checker 的签名默认值（见 [checker](<./checker.md>)）。

## 9. 错误约定

~~~text
ApplicationError
└── NavigationError
    └── ManualUpdateRequiredError
~~~

| 错误 | 定义位置 | 触发条件 | 处理者 | 是否可重试 |
| --- | --- | --- | --- | --- |
| `NavigationError` | `types.py` | 认不出当前页、没有可达路径、到达确认失败、标签切换失败、启动超时 | dispatch（`startup.ensure_ready`） | 是（可 SL 一次） |
| `ManualUpdateRequiredError` | `types.py` | 检测到游戏更新 | dispatch 转 `ManualRepairRequiredError` | 否，重启无效 |

导航器不吞异常、不静默降级；失败一律抛给调用方。

## 10. 日志约定

通道为 `ui.navigation`（service）、`ui.navigation.executor`（executor）。

| 级别 | 记录内容 |
| --- | --- |
| `INFO` | 跨页面路径的开始与完成、回退、遍历识别当前页的结果 |
| `WARNING` | 遍历识别不到任何页面 |
| `DEBUG` | 逐边前进/后退、到达确认与标签确认（见 [executor](<./executor.md>)） |
| `ERROR` | 本模块不记录（失败以异常交给上层） |

导航 service 记录跨多个页面的完整路径；单页的边动作由页面方法记录，service 不重复记录同一条边。

## 11. 公开出口和调用边界

### 11.1 稳定出口

| 出口 | 来源 | 调用者可以做什么 | 调用者不能做什么 |
| --- | --- | --- | --- |
| `service.NavigationService` | `service.py` | 构造导航器，调用三个公开入口 | 调用 `_current_page` 等私有实现 |
| `types.PageName` | `types.py` | 表达目标页面 | 把未接入页面当作可用目标 |
| `types.NavigationError` / `ManualUpdateRequiredError` | `types.py` | 捕获并决定恢复 | 依赖错误消息文本 |
| `types.NavTarget` / `NavTab` | `types.py` | 构造边与标签数据 | 在调用方拼装导航路径 |

`navigation/__init__.py` 的 `__all__` 为空：调用方直接从 `service` 导入（见 2.3 的循环导入说明）。

### 11.2 内部内容

`registry` 的三张注册表、`executor` 的私有方法与模块级常量、`service._current_page`、
各 checker 子包的 `checker.py` 及其内部辅助都是内部内容。

## 12. 模块维护方法

### 12.1 接一个新页面（四步）

1. `types.PageName` 加成员（值写中文页面名，与日志一致）；
2. 按 [checker](<./checker.md>) 的规矩写识别入口并从子包入口导出；
3. 在 [registry](<./registry.md>) 的 `_PAGE_CHECKERS` 注册确认；
4. 在 `_NAV_TARGETS` 至少补一条入边与一条出边。

做完这四步，`navigate_to(PageName.XXX)` 立即可用：算路、点击、前后确认、记栈都是现成的。

### 12.2 加一条边 / 一个标签

只改 [registry](<./registry.md>) 的数据表，不写转发函数。加边记得补反方向。

### 12.3 加一个每日浮窗

`PageName` 加成员 → 写 checker → 注册确认 → 在浮窗链里插一条 `confirm=False` 的边 →
把原本指向主页的边改指向新浮窗。

### 12.4 每日浮窗链（设计说明）

浮窗不是 service 里的私有流程，而是几个普通页面 + 几条普通边：

~~~text
每日公告 → 每日奖励 → 每日奖励确认 → 主页
~~~

- 每一步都「先问 checker 再做」：浮窗不在就什么都不做，避免空点；
- 除链尾外所有边 `confirm=False`：中间步的「到没到」取决于下一个浮窗在不在，静态判不了；
- `home.read_home_layer` 一帧读七个模板判当前层：有浮窗就返回浮窗层，因此 `navigate_to(HOME)` 会自然走这条链；
- 到达首页或侧边栏时，若三个每日浮窗标记不齐，执行器先停 3 秒等浮窗弹出，再做判层与
  `on_arrival` 记账；标记齐了直接跳过等待；
- 浮窗标记只在真正处理掉（关闭/领取/确认并确认消失）后写入，不做「回到主页就当作已处理」的推断。

已知边界：浮窗目前只弹在主页，所以「有浮窗 ≈ 在主页」这个简化成立；非主页也弹浮窗时需要重新设计。

### 12.5 页面内标签

标签不是页面，不参与算路。建模、到达确认分支与「为什么不把标签当页面」见
[registry](<./registry.md>) 第 6 章与 [executor](<./executor.md>) 第 7 章。

### 12.6 改某页的识别节奏

改该 checker 的签名默认值，或由调用方在 `navigate_to` 时传参覆盖；注册表不参与配节奏。

### 12.7 参数传入与穿透规则

| 参数 | 来源 | 规则 |
| --- | --- | --- |
| `**params` | 调用方经 `navigate_to` 传入 | 由 [executor](<./executor.md>) 原样透传给边动作 |
| `tab` | `params` 或边的 `tab` 字段 | 只作用于最后一跳 |
| `server` / `stage` | 调用方传业务值 | 位置与落点由边内部现算，调用方不预计算 |
| 活动玩法与章节绑定 | `ctx.read_event_type` / `read_event_stage` | 由 checker 读取，调用方不预先算好再传 |

### 12.8 删减能力或文件

先 grep 确认没有调用方（含测试、工具与文档），再删实现、删注册项、修正父子文档引用，最后跑门禁。

### 12.9 与 dispatch 的分工

dispatch 决定何时启动、何时 SL、按配置决定是否换区；导航器负责识别与点击。
因此 dispatch 的代码里不出现任何 checker 调用。

## 13. 验收门禁

| 检查 | 手段 | 最近结果 |
| --- | --- | --- |
| 公共入口 import smoke | `python -c "from autowsgr.application.ui.navigation.service import NavigationService"` | 通过 |
| 静态检查 | `ruff check autowsgr/application/ui/navigation` | 无新增问题 |
| 导航器单测 | `pytest testing/application testing/common` | 187 passed |
| checker 单测 | `pytest testing/application/ui/navigation/checker` | 全绿 |
| 消费者回归 | `pytest testing/dispatch/test_startup.py testing/dispatch/context` | 全绿 |
| 实机链路（导航图遍历） | `python tools/debug_toolkit/main.py e2e --no-launch nav_chain` | 28/28 通过，边覆盖 28/49（含学院进出；活动未开放、登录段需 `--from-login`、出征准备页往返由下一条覆盖） |
| 实机链路（出征选图） | `python tools/debug_toolkit/main.py e2e --no-launch sortie_scan --shuffle --keep-going` | 44/44 通过（全 44 个章节×节点，随机顺序），单组合 9~23 秒、平均 14 秒 |
| 文档树与代码树对齐 | 本文件的子项表与 `navigation/` 目录一致 | 通过 |
| `git diff --check` | 无空白错误 | 通过 |
