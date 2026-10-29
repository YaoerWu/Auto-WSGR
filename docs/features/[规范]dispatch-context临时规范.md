# dispatch Context 临时规范

状态：临时生效（按业务链路增量收敛）

适用范围：AutoWSGR 新架构中由 `autowsgr.dispatch` 持有的任务上下文。

本规范用于在上下文管理器正式设计完成前，约束导航器、UI Controller、业务层、
处理器和其他需要跨步骤状态的模块。它只描述新的 dispatch Context，不要求旧架构
立即适配。

本规范不是要求先一次性完成 dispatch Context 的最终设计。新模块治理和 dispatch
Context 治理必须按同一条业务链路垂直推进：模块先提出实际需要的上下文，dispatch
同步提供最小可用能力，联调结果再回写本规范。未被当前链路证明需要的字段、接口和
恢复策略不得提前实现。

## 0. 规则优先级与旧架构关系

本规范继承：

- 项目根目录 `AGENTS.md`；
- `[规范]python-code-style.md` 的全部通用 Python 规则；
- 对应模块的专项规范。

本规范是用户明确要求的新架构临时协议，适用于新的 `dispatch` Context 重写。
旧文档中关于“暂不建立新的上下文状态源”的提案，在新的 dispatch Context 范围内
不再适用；旧文档仍然保留作为迁移记录，不作为新实现契约。

新模块统一接收 `ContextHandle`，不再分别接收 UI、runtime 和 dispatch 三套 Context。
`ContextHandle` 同时提供只读 runtime 服务绑定和任务状态访问；`ContextTemplate` 仍只初始化
任务状态，不保存 runtime 服务对象。

以下对象不再作为新模块的兼容上下文入口：

- `application.ui.controller.context.UIContext`；
- `application.runtime.context.GameContext` / `RuntimeContext` 作为独立模块参数；
- 旧处理器和旧调度器中的上下文字段；
- 现有 `dispatch.image_context` 的模板缓存上下文。

迁移期间，runtime composition root 可以把现有 `GameContext` 作为 runtime binding 的来源，
但不得将它继续作为新模块的第二个上下文参数传入。

`dispatch.image_context` 只负责模板加载缓存，不得直接扩展成任务上下文管理器。

同一优先级规范发生冲突时，必须暂停实现并报告冲突。

### 0.1 Python 规则继承

本规范继承 `[规范]python-code-style.md` 的全部通用 Python 规则。

本规范只补充：

- dispatch Context 的目录和文件职责；
- ContextManager 的公开入口和内部实现边界；
- 上下文模板、作用域、句柄和业务契约的调用关系；
- 业务链路如何按垂直切片增量扩展 Context。

除非本文件明确写出“覆盖 Python 规范第 X 条”，否则 Python 全局规范继续生效。
上下文专项规则可以收紧全局规则，但不得在没有明确标记的情况下改写全局规则。

## 1. 模块目标

`dispatch Context` 是新架构唯一的模块级上下文入口，同时承载运行时服务引用和跨模块任务状态。

它只负责：

1. 绑定当前任务身份和 runtime service references；
2. 按统一模板懒创建任务状态；
3. 通过一个 `ContextHandle` 提供 runtime 服务与有业务语义的状态读写入口；
4. 校验任务字段类型、生命周期和读写权限；
5. 在任务结束时关闭任务状态并释放本作用域持有的 runtime 引用。

它不负责：

- 页面识别；
- 页面导航；
- 设备操作；
- 业务流程编排；
- 重试、恢复或重启；
- 错误处理决策；
- 向其他模块发送隐式回调通知；
- 创建、连接、断开或销毁设备、OCR 等 runtime 服务；
- 保存无限量截图、OCR 历史或日志历史。

上下文管理器是 runtime 引用和任务状态的访问基础设施，不是 runtime 服务工厂或业务处理器。

## 1.1 目录结构和文件职责

新的 Context 实现统一放在 `dispatch/context/`。第一阶段目标结构如下：

```text
autowsgr/dispatch/
├── __init__.py                 # dispatch 稳定出口，不放上下文实现
├── context/
│   ├── __init__.py             # ContextManager 和 context 门面出口
│   ├── manager.py              # 作用域、runtime 引用绑定、懒创建、读取、写入、关闭
│   ├── template.py             # ContextTemplate、字段规格和默认值
│   ├── runtime.py              # RuntimeBindings 服务引用协议
│   ├── state.py                # ContextManager 私有状态模型
│   ├── errors.py               # dispatch Context 专用错误
│   └── contracts/              # 按业务链路增量增加的跨模块状态契约
│       ├── __init__.py
│       ├── navigation.py       # 导航链路实际需要的状态
│       ├── combat.py           # 战斗链路需要时再创建
│       └── logistics.py        # 后勤链路需要时再创建
├── executor.py                 # 任务执行器基类：承接断点信号，终止后清栈回主页
├── processor.py                # 请求识别、排队和调度，不保存第二套 Context
├── registry.py                 # 执行器注册和构造
├── image_context.py            # 模板缓存上下文，不属于任务 Context
└── legacy_scheduler/           # 旧调度实现，迁移期间隔离
```

目录扩展规则：

- `context/` 是唯一的跨模块上下文实现位置；
- 业务模块需要跨步骤持有的新字段，放入 `context/contracts/<domain>.py`；
- 只在单个模块或单次调用内使用的数据，留在原业务模块，不得搬入 Context；
- `manager.py` 只管理生命周期和状态访问，不放战斗、导航或后勤业务逻辑；
- `template.py` 只定义字段规格和初始化规则，不保存可变运行时状态；
- `state.py` 是内部实现，业务模块不得直接导入；
- `contracts/` 中只放跨模块状态的数据契约，不放操作、识别、流程或设备调用；
- 只有真实业务链路需要时才增加领域契约文件，不预先创建空的 combat、logistics
  或其他领域文件。

新的业务模块不能在自己的 `page.py`、`recognition.py`、`workflow.py`、`operations.py`
或 `constants.py` 中保存跨模块 Context 字段。它应当先在任务切片中声明需求，再由
`dispatch/context/contracts/` 提供契约。

### 1.1.1 公共出口

业务模块只允许通过 Context 公共出口调用：

```python
from autowsgr.dispatch.context import context
```

测试和 dispatch 组装层可以额外导入 `ContextManager` 和 `ContextTemplate`。业务模块
不得导入 `manager.py`、`state.py`、私有字段或内部存储对象。

`context/__init__.py` 只导出稳定的公共对象，不放业务实现；`dispatch/__init__.py`
是否转出 Context 能力，必须等入口稳定后再决定，不得同时维护两套等价出口。

### 1.1.2 依赖方向

```text
Runtime composition root ──创建并注入服务引用──→ dispatch Context scope
dispatch.context ──标准库、system 错误、中性任务契约──→ ContextHandle
application / business / navigation / controller / common.vision ──只接收──→ ContextHandle
```

`dispatch.context` 可以持有 opaque runtime service references，但不得导入或构造具体的 UI、设备、
OCR、配置或业务实现。runtime composition root 负责创建、连接和断开服务；dispatch 只绑定、访问和
释放作用域中的引用。领域任务状态契约仍使用中性数据类型，避免循环依赖。

### 1.1.3 测试和文档位置

上下文实现的单测放在：

```text
testing/dispatch/context/
├── test_manager.py
├── test_template.py
└── test_contracts.py
```

业务链路的联调测试仍放在对应的 `testing/ui`、`testing/business` 或 `testing/dispatch`
目录，不把业务行为全部搬进 Context 单测。正式架构说明后续放在
`docs/AutoWSGR3.0/` 下按代码层级维护的 `<模块名>.md`，本文件只作为临时实施协议。

## 2. 基本术语

### 2.1 ContextManager

由 `dispatch` 层持有的唯一上下文管理器。它绑定 runtime service references，并内部持有任务状态；
其他模块不得自行维护重复的 runtime Context 或跨模块状态副本。

### 2.2 ContextScope

一次任务链路的作用域标识。生产代码使用 `Request.request_id` 作为任务身份，
不得由页面模块重新生成任务 ID。

绑定作用域记录“当前正在执行哪个任务”以及该执行需要的 RuntimeBindings，不代表已经创建了完整任务状态。

### 2.3 TaskContext

按需创建的任务状态。它的生命周期从第一次请求创建开始，到任务关闭为止；它不保存 runtime service
references，这些引用由 ContextScope 单独持有。

### 2.4 ContextHandle

新模块唯一接收的上下文访问句柄。句柄通过 `ContextManager` 取得，提供只读的 `.runtime` service bundle
和任务状态的语义化读写入口；不得暴露内部字典、内部状态对象或可替换的引用。

### 2.5 ContextTemplate

由 dispatch 统一维护的不可变初始化模板，定义字段、类型、默认值、生命周期和
所有者。模块不得临时注册字段或传入自己的上下文结构。

### 2.6 RuntimeBindings

由 runtime composition root 组装的类型化、不可变服务引用集合。`bind()` 将其绑定到
ContextScope，`ContextHandle.runtime` 在作用域内返回该 bundle。dispatch 按 opaque 类型持有，
不导入 runtime 所有者中的具体服务类。

### 2.7 InterruptSignals

由 dispatch 注入作用域的一对让路开关（`pause`、`stop`，都是 `threading.Event` 引用）。
它不是任务事实，不参与 `ContextTemplate`；导航器只通过 `ContextHandle.check_interrupt()`
读取，不直接访问开关。

判定只有一份实现：`InterruptSignals.check()` 先看 `stop`（终止优先），再看 `pause`，
命中就抛 `TaskStopped` / `TaskPaused`。`ContextHandle.check_interrupt()` 与执行器基类的
等待出口都转调它，各层不再各写一遍判定。

## 3. 持有关系

```text
Dispatcher / Processor
        │ 取得 runtime services 并绑定任务
        ▼
ContextManager
        │ 绑定 ContextScope(runtime references + task identity/template)
        ▼
TaskContext（第一次 request 时懒创建，仅任务事实）
        │ 与 runtime references 共同提供
        ▼
ContextHandle(runtime + task state API)
        ├── Navigator
        ├── UI Controller
        ├── Recognition
        └── Business / Processor
```

`ContextVar` 如被使用，只允许保存当前作用域的句柄或作用域 ID，不允许保存完整
的可变上下文状态。真正的状态必须由 `ContextManager` 持有。

项目不得创建进程级的无任务全局 Context，也不得让每个模块各自创建 Context。

## 4. 生命周期协议

### 4.1 绑定任务

调度层在任务链路入口绑定任务身份：

```python
with context.bind(
    request.request_id,
    template=ContextTemplate.for_task(request.task_type),
    runtime=runtime_bindings,
    interrupt=interrupt_signals,
):
    run_task()
```

`bind()` 必须满足：

- 任务 ID 非空且稳定；
- 只绑定作用域，不提前创建完整上下文；
- 有 runtime 服务需求的任务必须绑定对应 RuntimeBindings；不在 dispatch 内构造或销毁服务；
- 同一执行作用域内不得绑定另一个不同任务；
- 需要让路（暂停、终止、插队）的任务必须绑定 `InterruptSignals`；不绑定时 `check_interrupt()`
  直接返回，等于这条链路没有断点；
- 退出作用域时恢复上一级作用域，不遗留当前任务身份。

### 4.2 请求上下文

链路上的代码需要跨步骤状态时请求上下文：

```python
ctx = context.request()
```

`request()` 的规则：

- 当前任务第一次调用时，根据统一 `ContextTemplate` 创建上下文；
- 同一任务后续调用返回同一上下文句柄；
- 没有绑定任务时直接抛出上下文错误；
- 不因为缺少字段而静默创建第二个上下文；
- 不允许调用方替换当前上下文。

这意味着任务初始化阶段可以只绑定任务身份，具体链路在真正需要时再创建上下文。

### 4.3 关闭上下文

任务作用域退出时由 `ContextManager.bind()` 统一关闭和释放引用：

```python
with context.bind(task_id, template=template, runtime=runtime):
    run_task()
```

异常、停止和正常返回都会执行 `bind()` 的 finally 清理。`context.close()` 仅用于任务需要在
作用域内提前关闭状态的情况，不替代退出绑定作用域。

关闭后：

- 句柄失效；
- 读取和写入都必须失败；
- 不得自动恢复为上一次任务；
- 是否保存摘要由调度层决定，不由 ContextManager 私自持久化。

异常、停止、取消和正常结束都必须经过关闭路径。

## 5. 模板和字段规则

ContextTemplate 至少需要描述：

| 属性 | 语义 |
| --- | --- |
| 字段名 | 稳定的业务名称，不使用任意字符串键 |
| 类型 | 运行时允许的值类型 |
| 默认值 | 未产生事实时的明确状态 |
| 生命周期 | 任务级、步骤级或作用域级 |
| 写入者 | 唯一允许写入该字段的模块 |
| 读取者 | 允许读取该字段的模块 |
| 清理规则 | 任务关闭或步骤完成时的处理方式 |

字段必须区分“未产生结果”和“结果为空”。不得用静默的 `None` 或空字典掩盖
上下文尚未初始化、字段不存在或识别失败。

新增字段必须先修改 ContextTemplate 和本规范对应的字段表，再修改调用方。
禁止模块在运行时动态注册字段。

## 6. 第一阶段字段边界

ContextHandle 统一提供两类内容，但必须分开持有：

| 内容 | 位置 | 约束 |
| --- | --- | --- |
| RuntimeBindings | ContextScope，由 runtime composition root 注入 | 只保存运行时服务引用，不复制或管理其生命周期 |
| TaskContext | 按 `ContextTemplate` 懒创建 | 只保存跨模块、跨步骤的任务事实 |
| InterruptSignals | ContextScope，由 dispatch 注入 | 只保存 `pause` / `stop` 两个 Event 引用，是让路信号，不是任务事实；`check()` 是唯一的判定实现 |

RuntimeBindings 的字段按当前真实消费者增量定义，例如设备控制器、配置、OCR 引擎或
其他稳定运行时服务。dispatch core 只持有 opaque bundle，不导入这些服务的具体实现。

旧 UIContext 字段按职责迁移，不整体复制为 TaskContext 字段：

| 旧字段 | 新 Context 归属 |
| --- | --- |
| `ctrl`、`config`、`ocr`、`ship_ocr` | `ContextHandle.runtime` 中的 runtime service references |
| `record_screenshot()`、`latest_screenshot` | `ContextHandle.record_screenshot()` / `read_latest_screenshot()` |
| `current_page` | `ContextHandle.set_current_page()` / `read_current_page()` |
| `ui_stack` | 旧 navigation stack 保持旧实现边界；新路由使用显式页面和路由事实 |
| `daily_overlay_checked` | 仅在真实跨步骤读取者和唯一所有者确认后增加任务字段 |

TaskContext 第一阶段只允许收集跨模块编排确实需要的状态：

| 字段类别 | 典型内容 | 主要写入者 |
| --- | --- | --- |
| 任务身份 | `request_id`、`task_type`、请求来源 | dispatch |
| 活动任务参数 | `event_type`、`event_stage`（由 YAML 任务提供） | dispatch（bind 时随模板注入，导航器只读） |
| 导航状态 | 当前页面、目标页面、当前路由步骤 | Navigator |
| 观测结果 | 最近一次截图、页面识别结果、识别事件 | dispatch / Navigator |
| 操作结果 | 最近一次页面操作结果或异常事实 | dispatch / Controller 编排层 |
| 任务状态 | running、paused、stopped、completed、failed | dispatch |
| 错误事件 | 错误类型、发生步骤、可供上层处理的事实 | dispatch |

以下内容不得放入 TaskContext 或 ContextTemplate：

- 页面坐标、模板路径和页面私有常量；
- Controller 的私有缓存；
- 模块内部中间变量；
- 全量截图历史和全量 OCR 历史；
- 跨任务业务累计数据；
- GUI 状态和持久化用户配置。

设备对象、OCR 引擎和配置对象可以作为 RuntimeBindings 的只读引用通过 ContextHandle 提供，
但不得复制进 TaskContext，也不得由 ContextManager 构造、连接、断开或销毁。新模块只接收
ContextHandle，不再把 GameContext、RuntimeContext 或 UIContext 作为第二个上下文参数传入。

## 7. 字段所有权

上下文只保存事实，不代替事实的产生者做决定。

RuntimeBindings 与任务事实分开：runtime composition root 是服务引用的唯一创建者和绑定者；
ContextManager 负责作用域内引用访问，不改变服务状态或代替服务执行操作。

| 事实 | 产生者 | Context 的职责 |
| --- | --- | --- |
| 截图 | 设备/调度流程 | 保存最近一次或受控引用 |
| 页面识别结果 | checker / recognition | 保存返回事实，不重新识别 |
| 当前页面 | Navigator | 保存导航器确认后的状态 |
| 目标页面 | 业务入口 / Navigator | 保存任务目标，不修改业务意图 |
| 路由步骤 | Navigator | 保存步骤和执行结果 |
| Controller 操作结果 | Controller 返回值 | 保存结果，不执行下一步 |
| 错误 | 产生错误的编排层 | 保存错误事实，不决定恢复策略 |
| 任务终态 | dispatch | 关闭并清理上下文 |

recognition 只能返回识别结果，不能直接把“当前页面”写成已确认事实。
Navigator 只能写入自己确认过的页面状态。

## 8. 公共接口边界

新模块的正式入口暂定为 `autowsgr.dispatch.context`。ContextHandle 是唯一模块上下文，
第一阶段只允许出现以下语义类别的入口：

```text
bind(scope_id, template, runtime)
request()
close()

ctx.runtime
record_screenshot(...)
read_latest_screenshot()
read_current_page()
set_current_page(...)
read_target_page()
set_target_page(...)
read_event_type()
read_event_stage()
record_route_step(...)
record_result(...)
record_error(...)
check_interrupt()
```

`ctx.runtime` 返回本作用域绑定的只读 RuntimeBindings；具体字段由 composition root 的
runtime contract 定义。实际 Python 名称以后以实现为准，但必须保持上述所有权和生命周期语义。

禁止提供以下形式的生产入口：

```python
context.get('anything')
context.set('anything', value)
context.data['anything'] = value
```

需要通用访问能力时，先证明现有语义入口无法表达，再扩展 ContextManager 契约。

## 9. 模块调用关系

```text
业务层 ──业务参数──→ dispatch Context / Navigator
Navigator ──截图与导航事实──→ dispatch Context
Navigator ──每跳一次断点检查──→ dispatch Context（check_interrupt，收到信号就抛）
checker ──识别结果──→ Navigator
UI Controller ──操作结果/异常──→ Navigator 或 dispatch
状态机 ──只读取 Context 事实──→ 下一步决策
ContextManager ──不反向调用任何业务模块
```

上下文不得通过回调主动通知 Navigator 或 Controller。调用方通过返回值和下一次
读取获得状态变化；恢复、重试和重启由 dispatch 或业务编排层决定。

## 10. 错误协议

上下文错误属于 dispatch 错误域，具体错误继承 system 提供的 `DispatchError`。
至少需要区分：

- `ContextNotBoundError`：当前没有绑定任务；
- `ContextNotInitializedError`：请求的上下文或字段尚未初始化；
- `ContextClosedError`：任务已经关闭；
- `ContextFieldError`：字段不存在、类型不符或值非法；
- `ContextOwnershipError`：调用方没有字段写权限；
- `ContextScopeError`：作用域嵌套或任务身份不合法。

错误必须 fail closed。不能通过返回空值、自动重建上下文或回退到旧 `GameContext`
来掩盖生命周期错误。

## 11. 增量联调规则

dispatch Context 的实现与业务模块治理属于同一个交付切片，不拆成“先完成一个
万能 Context，再等待业务模块适配”的两个阶段。

每条新业务链路开始前，负责模块必须先列出：

- 需要读取的上下文事实；
- 需要产生并跨步骤保留的上下文事实；
- 每个事实的唯一写入者和读取者；
- 创建、成功、失败、暂停和停止时的生命周期；
- 当前链路能够验证的最小错误行为。

然后在同一条链路中完成以下工作：

1. 在 dispatch ContextTemplate 中增加当前链路确实需要的字段；
2. 增加与字段业务语义对应的 ContextManager 入口；
3. 改造当前业务模块通过该入口读写，不创建本地副本；
4. 联调并验证正常、异常和清理路径；
5. 将已验证的字段、所有权和调用关系回写本规范。

后续链路可以根据真实调用证据微调已有 Context 契约，但必须说明变更原因、影响的
已有消费者和验证结果。不得为了保留未经验证的旧形态而增加兼容别名、第二套状态源
或隐式 fallback。

### 11.1 第一条联调链路

第一条联调链路按以下顺序迁移：

1. runtime composition root 创建服务，再由 dispatch 在任务入口绑定 `Request.request_id`、模板和 RuntimeBindings；
2. Navigator 首次调用 `context.request()`，验证统一 ContextHandle 和任务状态懒创建；
3. checker 返回页面识别结果，Navigator 记录确认后的页面；
4. UI Controller 返回操作结果，dispatch 记录结果；
5. 任务正常、异常、停止三条路径都退出 `context.bind()`，由统一 finally 清理状态和 runtime 引用；
6. 新模块只接收 ContextHandle，不再单独接收 UIContext、RuntimeContext 或 GameContext；
   旧 GameContext 仅可在 composition root 作为服务引用来源。

ContextManager 关闭任务状态并释放作用域持有的服务引用，但不负责 disconnect、OCR 销毁或配置清理；
这些资源仍由 runtime composition root 按各自生命周期释放。

## 12. 每条链路的验收门禁

ContextManager 实现至少必须通过以下检查：

- 未绑定任务时请求上下文确定性失败；
- 同一任务第一次请求懒创建，后续请求得到同一状态；
- 两个任务的状态互不污染；
- 关闭后句柄不可读写；
- 异常退出仍然清理作用域；
- 不同任务不能覆盖当前作用域；
- 字段类型和写入权限得到校验；
- RuntimeBindings 只能在绑定作用域内读取，未绑定或关闭后访问必须失败；
- ContextManager 关闭时释放服务引用但不调用服务的资源清理方法；
- RuntimeBindings 与 ContextTemplate/TaskContext 状态存储互相隔离；
- ContextManager 不调用 Navigator、Controller 或业务层；
- 新模块没有直接访问内部字典；
- `dispatch.image_context` 仍只负责模板缓存。

除上述基础门禁外，每条业务链路交付时还必须确认：

- 业务模块和 dispatch Context 的变更属于同一个垂直切片；
- 当前 Context 字段均有真实调用方，没有预留空接口；
- 业务模块没有自行创建、复制或清空上下文；
- 联调失败时能够区分业务失败、上下文生命周期错误和设备/识别错误；
- 联调结束后，临时规范中的字段表和调用关系与实际代码一致。

本规范是临时协议。正式架构文档、模块拆分和跨任务持久化策略确认后，必须更新
本文件状态并给出替代文档，不得让“临时”接口无限期成为隐式公共契约。
