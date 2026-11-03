# application/navigation —— 导航器

源码：`autowsgr/application/navigation/`
上级：[架构总览](../../README.md) · 同级：[controller](../controller/README.md)

## 1. 模块定位

**负责**：把"我要去某个页面"变成一串真实点击。它给出页面坐标系（33 个 `PageName`）、可达图（谁点一下能到谁）、逐边执行器（点完确认到没到、记导航栈），以及启动阶段的登录流程。

**不负责**：

- 不认识页面细节——"这一页是不是后院"由 `application.controller` 的 checker 回答；
- 不写点击坐标——点哪里由 controller 的 `page.py` 决定；
- 不做业务判断——要不要去、去了做什么由 dispatch / business 决定。

## 2. 包内文件

| 文件 | 职责 |
| --- | --- |
| `__init__.py` | 空壳，`__all__ = []`；**不导出实现**，避免 controller ↔ navigation 循环导入 |
| `types.py` | 页面名与导航契约：`PageName`、`NavTarget`、`NavTab`、两个错误类型。零上层依赖，controller 可安全导入 |
| `registry.py` | 识别域、逐页 checker、页内标签、导航边四张表 + 查询函数（BFS 寻路） |
| `executor.py` | 逐边执行：点一步、确认到没到、记栈、检查让路 |
| `service.py` | 对外三个动作：`navigate_to` / `navigate_back` / `navigate_to_login` |

调用链固定为 **service → executor → registry → controller**，反向只有 `container` 注入的那个 `ctx`。

## 3. 页面模型

### 3.1 PageName（33 个）

成员值是游戏里显示的中文名，用于日志与断言报错。按界面归属分组：

| 组 | 成员 |
| --- | --- |
| 启动 | `LOGIN_PAGE` 登录页面、`SERVER_SELECT` 区服选择页面 |
| 主页 | `HOME`、`HOME_NEWS`、`HOME_REWARD`、`HOME_REWARD_CONFIRM` |
| 出征家族 | `SORTIE_MAP`、`EXERCISE`、`EXERCISE_RIVAL_CONFIRM`、`EXPEDITION`、`CAMPAIGN`、`DECISIVE_BATTLE` |
| 出征准备 | `BATTLE_PREPARATION`、`DECISIVE_BATTLE_PREPARATION`、`EXERCISE_PREPARATION`、`CAMPAIGN_PREPARATION` |
| 侧边栏 | `SIDEBAR`、`BUILD`、`BUILD_SUBMENU`、`INTENSIFY`、`INTENSIFY_SUBMENU`、`FRIEND` |
| 后院 | `BACKYARD`、`ACADEMY`、`BATH`、`CANTEEN`、`RANK_ROOM`、`RANK_SKILL_LIST` |
| 任务 | `MISSION`、`MISSION_REWARD_CONFIRM` |
| 活动 | `EVENT_MAP`、`EVENT_STAGE_OVERLAY` |

其中 `HOME_NEWS` / `HOME_REWARD` / `HOME_REWARD_CONFIRM` / `EXERCISE_RIVAL_CONFIRM` / `EVENT_STAGE_OVERLAY` 是**浮窗**：盖在某一页上，属于"层"不属于"栈"，导航器只把浮窗底下那页记进栈。

### 3.2 导航契约

```python
@dataclass(frozen=True, slots=True)
class NavTarget:
    target: PageName             # 这条边通向哪一页
    action: Callable[..., None]  # 点一下，可接收调用方透传的参数
    description: str = ''        # 边说明，排障日志直接打印
    confirm: bool = True         # 浮窗链中间步判不了"到没到"，置 False 跳过确认
    tab: str | None = None       # 到达后要落在哪个页内标签

@dataclass(frozen=True, slots=True)
class NavTab:
    click: Callable[..., None]    # 点这个标签
    checker: Callable[..., bool]  # 确认标签已激活
    description: str = ''
```

`tab` 描述"到这一页之后停在哪"，标签本身不是页面，不参与路径计算。

### 3.3 错误

```text
ApplicationError
└── NavigationError                导航没走通：路径不存在、选章卡住、启动超时
    └── ManualUpdateRequiredError  游戏需要更新，重试无用，交人工
```

上层只抓 `NavigationError`；`ManualUpdateRequiredError` 要单独分支——它意味着"别重试，叫人"。

## 4. 识别表与可达图（registry.py）

四张表是导航器唯一的事实来源。

### 4.1 识别域（3 个）

同域页面共用一套画面框架，一帧能读完本域所有层，所以按域探测而不是逐页扫描：

| 域探针 | 域内互斥页面（10 个） | 叠在上面的浮窗（4 个） |
| --- | --- | --- |
| `home.read_home_layer` | HOME | HOME_NEWS、HOME_REWARD、HOME_REWARD_CONFIRM |
| `sortie.read_sortie_layer` | SORTIE_MAP、EXERCISE、EXPEDITION、CAMPAIGN、DECISIVE_BATTLE | EXERCISE_RIVAL_CONFIRM |
| `battle_preparation.read_battle_preparation_layer` | BATTLE_PREPARATION、DECISIVE_BATTLE_PREPARATION、EXERCISE_PREPARATION、CAMPAIGN_PREPARATION | 无 |

域内页面与浮窗集合都从域表推导，**不要手写名单**。

### 4.2 逐页确认（18 项）

值统一收 `(ctx, *, absent=False, ...)`：`absent=False` 判出现，`True` 判消失。覆盖 LOGIN_PAGE、SERVER_SELECT、EVENT_MAP、EVENT_STAGE_OVERLAY、SIDEBAR、BUILD_SUBMENU、INTENSIFY_SUBMENU、BUILD、INTENSIFY、FRIEND、MISSION、MISSION_REWARD_CONFIRM、BACKYARD、CANTEEN、ACADEMY、RANK_ROOM、BATH。船池页 `SHIP_SELECTION` 也有确认入口，但它不进导航图，只用来在建栈时认出"停在这里"。

33 个页面里只剩 `RANK_SKILL_LIST` 没有 checker：执行器到这一页跳过确认，只能靠"点了之后画面变了"间接判断。

### 4.3 页内标签（4 页 9 个）

| 页面 | 标签 |
| --- | --- |
| SORTIE_MAP | sortie、exercise、expedition、campaign、decisive（互斥；远征可收时进入会停在远征，所以默认标签也登记） |
| EXERCISE | exercise |
| BUILD | destroy |
| INTENSIFY | remold、skill |

键与各页面控制器里标签枚举的 name 小写形式一致。

### 4.4 导航边（31 个起点 / 57 条边）

只写非默认路径的边，每条一行 `NavTarget`；一行写不下的动作写成具名函数放在"动作"区（`_close_daily_news`、`_settle_to_sidebar`、`_sortie_map_to_preparation`、`_exercise_to_rival_overlay`、`_event_map_to_overlay` 等）。

**船池页不进图**：只有决定进船池的模块（换船、强化、拆解等）知道怎么用它，导航器不提供进出的边。空栈停在船池页时，由建栈流程先退一步再识别落点（见 5.1）。决战准备页与战役准备页目前只有返回边、没有进入方向的边——这两页的入口点击还没接。

### 4.5 查询函数

```python
get_targets(page) -> tuple[NavTarget, ...]     # 某页的直达边
get_checker(page) -> Callable | None           # 到达确认入口；无 checker 返回 None
get_tabs(page) -> dict[str, NavTab]
probe_domains(ctx, *, attempts=1, interval_seconds=0.2) -> tuple[PageName, ...]  # 一帧读完所有域
is_domain_page(page) -> bool
domain_of(page) -> int | None
is_overlay_page(page) -> bool
depth_of(page) -> int                          # 距主页最短跳数，@cache；不可达 -1
find_path(source, target, *, exclude=frozenset()) -> tuple[NavTarget, ...]  # BFS
on_arrival(ctx, page) -> None                  # 到达后刷会话记账（到 HOME 记"浮窗已清"）
popups_all_settled() -> bool
```

`find_path` 不可达抛 `NavigationError`，`exclude` 用来绕开"当前走不了"的页面；`depth_of` 带 `@functools.cache`，因为图写在代码里、运行期不变。

## 5. 执行与出口

### 5.1 一跳的流程（executor.py）

```text
walk_forward(path, params)
  └─ 逐条 NavTarget：
       action(**params)                      # 点（或执行一段页内动作）
       ├─ 边带 tab → _enter_tab(page, tab)    # 点标签 + 标签自己的 checker 确认，最多 2 次
       └─ confirm=True → _confirm_arrival(edge)
             ├─ 目标页在 3 秒内出现（域页面只等 2 秒）
             ├─ 有 checker：调 check_<page>(ctx)
             └─ 再等 1.2 秒，让入场动画走完、触摸不丢
       _record_page(page)                    # 记进导航栈
       _check_interrupt()                    # 让路只发生在边与边之间
```

节奏常量集中在 `executor.py` 顶部：`_ARRIVAL_SETTLE_SECONDS=3.0`、`_DOMAIN_ARRIVAL_SETTLE_SECONDS=2.0`、`_ARRIVAL_REST_SECONDS=1.2`、`_TAB_SETTLE_SECONDS=2.0`、`_TAB_CLICK_ATTEMPTS=2`、`_TAB_RETRY_INTERVAL_SECONDS=2.0`。

导航栈规则（`_record_page`）：浮窗不记；同域替换栈顶（换页不是又深一层）；跨域压栈。回主页由 dispatch 先 `clear_pages()`。

探测期 `_QUIET_DURING_PROBE` 临时关掉 `autowsgr.common.vision` 与 `autowsgr.application.controller` 的 DEBUG 日志，避免一帧刷屏。

### 5.2 对外入口（service.py）

```python
class NavigationService:
    def __init__(self, ctx: ContextHandle, *, session: SessionState | None = None,
                 checkpoint: bool = True) -> None: ...
    def navigate_to(self, target: PageName, **params: object) -> None: ...
    def navigate_back(self) -> None: ...
    def navigate_to_login(self) -> None: ...
```

- `navigate_to`：取当前页（栈顶优先，栈空扫一帧重建）→ 已经在这一页就直接返回 → 否则 `find_path` + `walk_forward`。
- 栈空重建时，若扫到的是导航图之外的页面（当前只有船池页），先点一次返回、重新扫一帧，用真实落点建栈：回退落到哪个准备页由游戏决定，不猜路径。最多退两步——船池退到准备页；若那是普通出征与活动共用的准备页，还要再退一步才能确定落在出征主页还是活动地图。退完仍在图外就抛 `NavigationError`。
- `navigate_back`：栈空抛 `NavigationError('导航栈为空，无法回退')`。
- `navigate_to_login`：启动专用，按"更新提示 → 黑屏/健康游戏 → 加载中"三段判断；更新提示命中抛 `ManualUpdateRequiredError('检测到游戏更新，需要人工处理')`；等登录页最多 60 次、间隔 1 秒，超时抛 `NavigationError('启动超时：未出现登录页')`。

### 5.3 上层接入点

| 调用方 | 用法 |
| --- | --- |
| `dispatch.startup.ensure_ready` | 冷启动：`navigate_to_login` → 区服选择 → 登录页（带 server）→ 主页 |
| `dispatch.executor._navigate_to_home` | 清空页面栈后回主页；失败退回 `ensure_ready` |
| business 各任务 | 直接 `navigate_to(PageName.XXX, **params)` |

## 6. 怎么维护

1. **加一个页面**：`types.py` 加成员 → controller 写 `check_<page>` → `registry.py` 登记到 `_DOMAINS`（成域探测）或 `_PAGE_CHECKERS`（逐页）→ `_NAV_TARGETS` 补进出边。四步缺一，页面就是孤岛。
2. **加一条边**：只改 `_NAV_TARGETS`，并写 `description`；动作一行 lambda 或具名函数放"动作"区。
3. **加标签**：`_TABS` 加一项，键用枚举 name 小写形式；同时页面控制器加对应枚举成员与 click。
4. **改等待节奏**：只改 `executor.py` 顶部常量，别在函数体里散写 `sleep`。
5. **不要让 `types.py` 依赖任何上层模块**：controller 也要导入 `PageName`，一旦反向依赖就循环。

## 7. 已知遗留（只报告，未改）

- `registry.py`:71 仍 `from autowsgr.application.ui.controller.home.event_page import EventPage`，新导航器反向依赖旧 UI 包；活动页迁移后应改为调用 controller 下的新入口。
- `RANK_SKILL_LIST` 没有 checker，也不在域表内，属于"到得了但确认不了"的页面。
- `DECISIVE_BATTLE_PREPARATION`、`CAMPAIGN_PREPARATION` 两页没有进入方向的边：只能从没接上的入口进，导航器目前到不了，只有返回一条出边。
- 日志通道仍是旧名 `ui.navigation`、`ui.navigation.executor`，与"按包路径命名"的约定不一致。
