# application-ui-navigation-registry 架构说明

版本：AutoWSGR-3.0 第 1 版
状态：生效
适用范围：`autowsgr/application/ui/navigation/registry.py`
实现基线：`codex/20260913-shiinaskuya-upgrade-7b3e`，2026-10-13（导航器样板去重）

## 1. 模块定位

registry 是 **application 层导航器**的注册中心与算路模块。它只回答三个问题：

1. 某一页怎么确认「到了」——页面确认表 `_PAGE_CHECKERS`；
2. 从某一页能直达哪里、怎么去——可达边表 `_NAV_TARGETS`；
3. 到达某一页之后可以落在哪个标签上——标签表 `_TABS`。

它明确不负责：点击坐标与设备操作（属于 UI 控制器）、识别规则（属于 [checker](<./checker.md>)）、
路径的执行与逐跳确认（属于 [executor](<./executor.md>)）、跨页面流程编排（属于 `service.py`）。

所有权：

- 三张注册表由本模块独占持有，运行期只读；
- 页面名与边数据模型由 `types.py` 定义；
- 算路结果是不可变元组，由调用方持有；
- 本模块没有运行时状态、没有配置、不记录日志。

## 2. 模块架构

### 2.1 文件形态

registry 是单文件模块，没有子目录，因此不拆分子文档：

~~~text
autowsgr/application/ui/navigation/
└── registry.py      # 常量 + 十一个查询入口 + 边动作 + 五张表
~~~

### 2.2 文件内部结构

文件按「常量 → 公开入口 → 边动作 → 数据表」排列，功能分区与代码中的分割线一致：

| 分区 | 内容 |
| --- | --- |
| 常量 | 五个模块级常量：动作用 3 个、标签用 1 个、查询用 1 个 |
| 查询入口 | 十一个公开查询函数，模块统一出口 |
| 边动作 | 一行数据写不下的边才写，共 8 个：每日浮窗 5 个、任务 1 个、活动地图 1 个、出征 1 个 |
| 识别表 | `_DOMAINS`（探针与它负责的页面成对登记，一域一帧一次判层）、由它派生的 `_DOMAIN_PROBERS` / `_DOMAIN_PAGES`、`_OVERLAY_PAGES`（浮窗名单）与 `_PAGE_CHECKERS`（只放逐页确认的普通页面） |
| 导航表 | `_TABS`（页面内标签）与 `_NAV_TARGETS`（可达边） |

表和边动作的顺序不能互换：表项要在定义时拿到现成的可调用对象，所以边动作必须写在表前面。
公开入口不受这个约束——函数体在调用时才解析模块全局，因此可以提到最前面。

### 2.3 依赖方向

~~~text
service / executor / checker 测试
        ↓
registry 的十一个查询入口
        ↓
五张表（读 registry 的模块全局）
        ↓
边动作
        ↓
types / checker / application.ui.controller
~~~

禁止方向：

- registry 不导入 `service.py` 或 [executor](<./executor.md>)（会形成循环）；
- 表与查询入口不做识别、不点击；边动作可以读事实、点一下，但不拼坐标、不写流程；
- 页面控制器不得反向导入 registry。

### 2.4 出口策略

稳定出口是十一个查询入口；三张导航表与域表、浮窗名单本身是模块私有数据，外部只能通过查询入口读取。
测试为了替换确认入口会直接改 `_PAGE_CHECKERS`、`_TABS`，这属于测试手段，不构成生产公开出口。

## 3. 能力总览

| 能力 | 对外入口 | 输入 | 输出 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- | --- | --- |
| 查询直达目标 | `registry.get_targets` | `PageName` | `tuple[NavTarget, ...]` | 返回该页全部出边 | 过滤、排序、执行 |
| 查询到达确认 | `registry.get_checker` | `PageName` | `Callable \| None` | 返回该页确认入口 | 调用它、处理失败 |
| 查询页面标签 | `registry.get_tabs` | `PageName` | `dict[str, NavTab]` | 返回该页非默认标签 | 标签切换 |
| 算路 | `registry.find_path` | 起点、终点、可选排除集 | `tuple[NavTarget, ...]` | 广度优先拼最短路径 | 执行路径 |
| 页面深度 | `registry.depth_of` | `PageName` | `int` | 从主页出发的最短跳数 | 参与算路结果 |
| 探测各域当前层 | `registry.probe_domains` | `ctx` | `tuple[PageName, ...]` | 每个域一帧读一次，返回命中层 | 逐页确认与排序 |
| 判断域页面 | `registry.is_domain_page` | `PageName` | `bool` | 该页是否由域探针负责 | 识别与执行 |
| 查询所在域 | `registry.domain_of` | `PageName` | `int \| None` | 页面属于哪个域；同域换页不换画面框架 | 判断该不该记栈 |
| 判断浮窗 | `registry.is_overlay_page` | `PageName` | `bool` | 该页是不是页面内的一层浮窗 | 关浮窗与建栈 |
| 到达记账 | `registry.on_arrival` | `ctx`、`PageName` | 无（写会话标记） | 回到干净主页时写每日浮窗标记 | 判层与点击 |
| 浮窗标记查询 | `registry.popups_all_settled` | 无 | `bool` | 三个每日浮窗是否都已处理 | 处理浮窗 |

## 4. 页面确认注册：_PAGE_CHECKERS

### 4.1 说明

表把页面名映射到「确认这一页到了」的入口，形状与调用约定：

~~~python
_PAGE_CHECKERS: dict[PageName, Callable[..., bool]] = {
    PageName.SIDEBAR: sidebar.check_sidebar_page,
    ...
}
~~~

取值统一收 `(ctx, *, absent=False, attempts, interval_seconds)`：`absent=False` 判出现（前识别），
`absent=True` 判消失（后识别）。识别节奏由各 checker 的签名默认值决定，注册表不参与配置。

### 4.2 当前覆盖

已注册 **17 个页面**。页面名表（`types.PageName`）共 33 个成员：14 个由域探针负责（见 [§4.3](#43-域探针)），
17 个逐页登记在本表，其余 2 个（军阶室技能列表、选择舰船）是尚未接入导航图的预留页面。

对未注册的页面调用 `find_path` 会抛 `NavigationError`（没有可达路径），这是预期行为，不是故障。

### 4.3 域探针

同族页面的标志物落在同一帧的同一块区域上，逐页调用会把同一帧读好几遍，因此按域聚合。当前三个域：

| 域 | 探针 | 一帧读什么 | 负责的页面 |
| --- | --- | --- | --- |
| 主页浮窗 | `home.read_home_layer` | 7 个浮窗/主页模板 | 主页、每日公告弹窗、每日奖励弹窗、每日奖励确认 |
| 出征域 | `sortie.read_sortie_layer` | 演习浮窗标题 + 5 个标签激活态模板（各配互不重叠 ROI） | 演习对手浮窗、出征页面、演习、远征、战役、决战页面 |
| 出征准备页 | `battle_preparation.read_battle_preparation_layer` | 4 个准备页模板（共用同一个 ROI） | 出征准备、决战准备、演习准备、战役准备 |

~~~python
_DOMAINS: tuple[tuple[Callable[..., tuple[PageName, ...]], frozenset[PageName]], ...] = (
    (home.read_home_layer, frozenset({ PageName.HOME, ... })),
    (read_sortie_layer, frozenset({ PageName.SORTIE_MAP, ... })),
    (read_battle_preparation_layer, frozenset({ PageName.BATTLE_PREPARATION, ... })),
)

_DOMAIN_PROBERS = tuple(prober for prober, _pages in _DOMAINS)
_DOMAIN_PAGES = frozenset(page for _prober, pages in _DOMAINS for page in pages)
~~~

探针和它负责的页面**成对登记在一张表里**，不再各写一份：漏登记一页会让探针返回的层
落进逐页分支、而那里没有它的确认入口，执行器会静默放行——这种错不会报错，只会认错页面。
派生出两张只读视图后，两张表不可能对不上。

`probe_domains(ctx)` 在每个域读一帧，把各探针返回的元组拼起来，得到这一帧能看到的全部层（由深到浅，没命中就是空元组）；
`is_domain_page(page)` 判断页面是否由探针负责；`domain_of(page)` 返回它属于哪个域，
执行器靠这个区分「同域换页只替换栈顶」和「跨域压一格」。由探针负责的页面不再登记到 `_PAGE_CHECKERS`。

每个探针返回**元组**而不是单个页面：浮窗出现时它背后的标签栏往往没被遮住，
`(EXERCISE_RIVAL_CONFIRM, EXERCISE)` 两层会同时命中。调用方因此分两种：

- 判「到没到目标页」：取 `max(layers, key=depth_of)` 比目标页，**不能用 `in`**；
- 判「标签切没切过去」：要求**严格相等** `== (目标页,)`。

域的划分原则是「一次点击只能把那组页面中的一个变成激活态」：五个标签互斥、四种准备页互斥，
它们共享同一块识别区域，所以一帧就能判定。

### 4.4 浮窗名单

~~~python
_OVERLAY_PAGES: frozenset[PageName] = frozenset({
    PageName.HOME_NEWS,
    PageName.HOME_REWARD,
    PageName.HOME_REWARD_CONFIRM,
    PageName.EXERCISE_RIVAL_CONFIRM,
})
~~~

浮窗是页面里的一层覆盖，不是独立页面，所以**不占导航栈**。执行器记栈时遇到名单里的页面直接跳过；
冷启动扫到浮窗时，`service._current_page` 先把它清掉再建栈，栈就落在它下面那层。
`is_overlay_page(page)` 是这份名单的唯一读取口。

新增浮窗页面时要同时把它放进域探针（否则扫不到）和这份名单（否则会占栈）。

### 4.5 维护规则

新增一个确认入口时：先在 [checker](<./checker.md>) 里写好入口并从包入口导出，再在这里加一行。
注册表不写转发函数、不包一层默认参数、不改写 checker 的节奏。

## 5. 可达边注册：_NAV_TARGETS

### 5.1 说明

每条边是一个不可变数据类 `types.py` 的 `NavTarget`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `target` | `PageName` | 这条边通向哪一页 |
| `action` | `Callable[..., None]` | 怎么去：一次点击，签名 `action(ctx, **params)` |
| `description` | `str` | 边说明，进日志与调试输出 |
| `confirm` | `bool` | 到达后是否做确认；浮窗链中间步置假 |
| `tab` | `str \| None` | 到达后要落在的页面内标签 |

**一条边默认就是一行数据。** 换页、点一下就走的写 lambda；一行写不下的才写具名边动作。
需要参数的边在 `action` 内部现算，调用方（dispatch）只传业务参数，例如区服那条边收的是
区服名，位置由边内部定位。

边动作是**连续动作**时（选章选节要连点十几下），中途不让路：断点只能放在动作内部
「所有点击做完、还没进下一页」的位置，由边动作自己调一次 `ctx.check_interrupt()`。
目前只有出征选章那条边这么做，理由见 [executor](<./executor.md>) §6。

### 5.2 当前规模

**55 条边、29 个有出边的页面**。按域分布：

| 起点 | 出边 |
| --- | --- |
| 登录页面 | 区服选择页面、每日公告弹窗（`confirm=False`） |
| 区服选择页面 | 登录页面 |
| 主页面 | 出征页面（`tab='sortie'`）、演习页面（`tab='exercise'`）、活动页面、侧边栏、任务页面、后院页面 |
| 每日公告弹窗 | 每日奖励弹窗（`confirm=False`） |
| 每日奖励弹窗 | 每日奖励确认（`confirm=False`） |
| 每日奖励确认 | 侧边栏、主页面 |
| 出征页面 | 出征准备页、演习页面、每日公告弹窗（`confirm=False`） |
| 演习页面 | 演习对手浮窗、每日公告弹窗（`confirm=False`） |
| 远征 / 战役 / 决战页面 | 每日公告弹窗（`confirm=False`），各一条 |
| 演习对手浮窗 | 演习准备页、演习页面 |
| 出征准备页 / 演习准备页 | 出征页面 / 演习页面 |
| 侧边栏 | 建造二级菜单、强化二级菜单、好友页面、主页面 |
| 任务页面 | 任务奖励确认（`confirm=False`）、每日公告弹窗（`confirm=False`） |
| 任务奖励确认 | 任务页面 |
| 后院页面 | 食堂、学院、军阶室、浴室、每日公告弹窗（`confirm=False`） |
| 四个二级页（食堂/学院/浴室/军阶室） | 每日公告弹窗（`confirm=False`）、后院页面 |
| 建造页面 / 强化页面 / 好友页面 | 每日公告弹窗（`confirm=False`） |
| 建造二级菜单 / 强化二级菜单 | 对应页面、主页面 |
| 活动页面 | 活动章节浮窗、每日公告弹窗（`confirm=False`） |
| 活动章节浮窗 | 活动页面 |

### 5.3 两条硬约定

1. **有来有回**：加了 `A → B`，通常也要有 `B → A`，否则进去出不来（`navigate_back` 也走它）；
2. **参数靠 `**params` 透传**：`navigate_to(target, **params)` 原样传进边的 `action`。

### 5.4 维护规则

只加一行数据。新增边后必须确认：

- 起点和终点都能被 `_PAGE_CHECKERS` 或域探针（`_DOMAIN_PAGES`）认出来；
- 目标页有回边；
- 需要参数时，参数在边内部现算，不在调用方算好再传。

## 6. 页面内标签注册：_TABS

### 6.1 说明

标签不是页面，不参与算路。它描述「到达这一页之后要落在哪个视图上」，形状为 `types.py` 的 `NavTab`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `click` | `Callable[..., None]` | 点击该标签 |
| `checker` | `Callable[..., bool]` | 判该标签是否激活 |
| `description` | `str` | 标签说明 |

只登记**非默认标签**：默认标签就是页面本身，页面级 checker 已经认它。

### 6.2 当前登记

| 页面 | 标签键 |
| --- | --- |
| 出征页面 | `sortie`、`exercise`、`expedition`、`campaign`、`decisive` |
| 建造页面 | `destroy` |
| 强化页面 | `remold`、`skill` |

出征页面把默认标签 `sortie` 也登记了，因为远征可收时进入会停在远征，需要一个切回来的入口。

### 6.3 维护规则

新增标签只改这一张表加一个 `NavTab`。**不要把标签升格成页面**：四个标签会多出 12 条互切边和 4 条回边，
而「每步都要确认」又不允许把标签降级成纯参数，`_TABS` 是保住两者的中间形态。

## 7. 算路：find_path

### 7.1 稳定入口

~~~text
registry.find_path(source: PageName, target: PageName, *, exclude: frozenset[PageName] = frozenset()) -> tuple[NavTarget, ...]
~~~

### 7.2 调用示例

~~~python
from autowsgr.application.ui.navigation import registry
from autowsgr.application.ui.navigation.types import PageName

path = registry.find_path(PageName.SORTIE_MAP, PageName.EVENT_MAP)
for edge in path:
    print(edge.description)
~~~

### 7.3 行为

广度优先、按出边顺序拼接最短路径；起点即目标返回空元组；没有路径时抛 `NavigationError`。
`exclude` 用于跳过已处理过的每日浮窗，让路径改走直连边。

### 7.4 维护规则

算路逻辑不需要随页面增减而修改：新页面只改数据表。若出现「同一目标有多条路径且需要选特定一条」，
优先在边上补齐约束，而不是在 `find_path` 里加特例。

## 8. 页面深度：depth_of

### 8.1 稳定入口

~~~text
registry.depth_of(page: PageName) -> int
~~~

### 8.2 行为

返回从主页出发的最短跳数，主页为 0；不可达页面返回 `_UNREACHABLE_DEPTH`（`1 << 30`），
保证它们在按深度降序的扫描里排在最后。

图写在代码里、运行期不变，因此结果用 `functools.cache` 记忆；进程重启后重算，值完全一样。

### 8.3 调用方

[executor](<./executor.md>) 的 `detect_layer` 按深度降序扫描全部页面，用它把覆盖层排在底层页面前面。

## 9. 统一配置

本模块无运行时配置。识别节奏属于各 checker 的签名默认值，不属于注册中心。

## 10. 错误约定

| 错误 | 定义位置 | 触发条件 | 处理者 | 是否可重试 |
| --- | --- | --- | --- | --- |
| `NavigationError` | `types.py` | `find_path` 找不到可达路径 | 调用方（dispatch 决定 SL 或人工处理） | 由上层决定 |

注册表自身不抛其他错误，也不吞异常。

## 11. 日志约定

本模块不记录日志。算路的开始与完成由 `service.py` 记录，逐边执行由 [executor](<./executor.md>) 记录。

## 12. 公开出口和调用边界

### 12.1 稳定出口

| 出口 | 来源 | 调用者可以做什么 | 调用者不能做什么 |
| --- | --- | --- | --- |
| `registry.get_targets` | `registry.py` | 读某页出边 | 修改返回的边、依赖边顺序做业务判断 |
| `registry.get_checker` | `registry.py` | 取确认入口并调用 | 依赖未注册页面有默认值 |
| `registry.get_tabs` | `registry.py` | 读某页标签 | 把标签当页面算路 |
| `registry.find_path` | `registry.py` | 算一条路径 | 在调用方自行拼路径 |
| `registry.depth_of` | `registry.py` | 读页面深度 | 用深度做业务分支 |

### 12.2 内部内容

`_PAGE_CHECKERS`、`_NAV_TARGETS`、`_TABS`、`_UNREACHABLE_DEPTH` 与全部 `_` 前缀动作为模块内部内容。
测试为替换确认入口直接改前两张表，这是测试手段，不构成生产出口。

## 13. 模块维护方法

### 13.1 新增一个可达页面

1. 在 `types.py` 的 `PageName` 加成员（值写中文页面名，与日志一致）；
2. 按 [checker](<./checker.md>) 的规矩写识别入口，并从包入口导出；
3. 在 `_PAGE_CHECKERS` 注册确认；
4. 在 `_NAV_TARGETS` 至少补一条入边和一条出边；
5. 跑 `testing/application/ui/navigation` 与 `testing/application/ui/navigation/checker`。

### 13.2 新增一条边

只往 `_NAV_TARGETS` 加一行，并补反方向。若这条边的目标不是「干净到达」，显式声明 `confirm=False` 并写明原因。
一行写不下的才写边动作，不要在 lambda 里堆流程。

### 13.3 新增一个标签

只往 `_TABS` 加一项。标签的点击动作走控制器的公开入口，确认入口走 checker。

### 13.4 新增一个每日浮窗

按顺序做：`PageName` 加成员 → 写 checker → 注册确认 → 在浮窗链里插一条 `confirm=False` 的边 →
把原本指向主页的边改指向新浮窗。

### 13.5 参数传入与穿透规则

| 参数 | 来源 | 规则 |
| --- | --- | --- |
| `**params` | 调用方经 `navigate_to` 传入 | 由 [executor](<./executor.md>) 原样透传给边动作 |
| `server` | 调用方传入区服名 | 边的 `action` 内部调 `login.resolve_server_index` 现算位置 |
| `stage` | 调用方传入章节标识 | 边的 `action` 内部解析难度与落点 |
| 活动玩法/章节绑定 | 由 `ctx.read_event_type` / `ctx.read_event_stage` 读取 | 边的 `action` 内部读，调用方不预先算好再传 |

### 13.6 删减注册项

先 grep 确认没有调用方（含测试与工具），再删表项、删边、修正父文档与协作方文档里的引用，最后跑门禁。

## 14. 验收门禁

| 检查 | 手段 |
| --- | --- |
| 公共入口 import smoke | `python -c "from autowsgr.application.ui.navigation import registry"` |
| 静态检查 | `ruff check autowsgr/application/ui/navigation/registry.py` |
| 模块单测 | `pytest testing/application/ui/navigation` |
| 边覆盖 | `python tools/debug_toolkit/main.py e2e --no-launch --event-type stage_push --event-stage EX1 nav_chain` |
| 文档与代码一致 | 本文件的边表与 `_NAV_TARGETS` 对齐；`git diff --check` |
