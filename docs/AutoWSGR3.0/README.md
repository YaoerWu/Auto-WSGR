# AutoWSGR 3.0 架构

本文档体系与主程序目录一一对应：每一层、每一个被单独维护的**包**各有一篇 md（以包为维度，包内的 checker.py / page.py 等文件在同一篇里说明，不单独成篇）。写的是**当前分支（codex/20260913-shiinaskuya-upgrade-7b3e）的真实代码**——所有路径、类名、函数名都在写之前对照源码核对过。

读法：先看本篇建立整体图景，再按目录点进对应文档。文档与源码冲突时以源码为准，并回头修文档。

---

## 1. 运行时四层

任务执行时只有四个角色在接力，它们构成主干：

| 层 | 目录 | 负责 | 明确不负责 |
| --- | --- | --- | --- |
| 业务层 | `autowsgr/business/` | 一次完整玩法：常规战、活动战、战役、演习、决战，以及远征、建造、奖励、烹饪、解装、修理 | 页面怎么走、按钮在哪、像素怎么比 |
| 导航器 | `autowsgr/application/navigation/` | 页面到页面的路由：算路径、执行跳转、确认到达、维护导航栈 | 坐标、业务流程、任务恢复 |
| 控制器 | `autowsgr/application/controller/` | 判定"现在是哪个页面/浮窗"、读取按钮中心、执行单次点击 | 页面之间怎么走、等待与重试编排 |
| 战斗·换船 | `autowsgr/application/combat/`、`autowsgr/application/controller/sortie/battle_preparation/ship_recognition/` | 战斗状态机与阶段推进；编队槽位识别 | 页面导航、任务调度 |

三块支撑面向全部四层：

| 支撑 | 目录 | 负责 |
| --- | --- | --- |
| 调度 | `autowsgr/dispatch/` | 任务注册与优先级、任务上下文（`ContextHandle`）、会话状态（导航栈、每日浮窗、区服）、启动编排 |
| 底座 | `autowsgr/common/` | `system`（日志/错误/文件/枚举）、`device`（连接/输入/截图）、`vision`（识别能力） |
| 接口 | `autowsgr/server/` | FastAPI 的 HTTP 与 WebSocket 入口 |

```text
                    ┌──────────────┐
        HTTP / WS ─►│    server    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │   dispatch   │  调度 · 上下文 · 启动
                    └───┬──────┬───┘
                        ▼      ▼
             ┌──────────────┐  ┌───────────────────────────────┐
             │   business   │─►│ 导航器 → 控制器 → 战斗·换船     │
             │   业务层      │  │ navigation  controller  combat │
             └──────────────┘  └───────────────┬───────────────┘
                                              ▼
                                       ┌──────────────┐
                                       │    common    │  system / device / vision
                                       └──────────────┘
```

## 2. 依赖方向

1. **只向下**：`server → dispatch`、`dispatch → application / business`、`business → application → common`。`common` 不导入任何上层模块（识别入口里对 `ContextHandle` 的引用只是 `TYPE_CHECKING` 标注）。
2. **只走公开入口**：跨层调用一律走对方包的 `__init__.py` 或 `service.py`；不 import 别人的私有函数、私有常量和内部执行器（详见各篇的"依赖关系"）。
3. **反向依赖只有一处**：`navigation` 要跨调用保存导航栈，因此 `registry/executor/service` 依赖 `dispatch.session`（会话状态）与 `dispatch.context`（任务上下文）。方向是"应用层读调度层的状态容器"，不是因为调度层懂导航。
4. `navigation/types.py` 不导入任何上层模块，所以控制器可以安全地 import 它来表达页面名，不会形成 `controller ↔ navigation` 循环。

## 3. 一次任务的主链路

以"开始一个任务、先确保回到主页"为例，真实调用顺序：

1. `autowsgr/server/routes/*` 接收请求 → `dispatch` 注册/派发任务。
2. `autowsgr/dispatch/processor.py` 在任务开始前调用 `dispatch.startup.ensure_ready(ctx)`（`autowsgr/dispatch/startup.py:43`）。
3. `ensure_ready` 构造 `NavigationService(ctx)`（`startup.py:56`），冷启动时依次 `navigate_to_login()` → `navigate_to(PageName.SERVER_SELECT)` → `navigate_to(PageName.LOGIN_PAGE, server=...)`，最后 `navigate_to(PageName.HOME)`。
4. `NavigationService.navigate_to`（`application/navigation/service.py:95`）从当前页出发，调 `registry.find_path` 做 BFS 算路，得到一串 `NavTarget` 边。
5. `NavigationExecutor.walk_forward`（`application/navigation/executor.py`）逐边执行：边动作点击 → `_confirm_arrival` 调控制器 `check_*` 确认到达 → `_record_page` 记栈。
6. 控制器的 `checker.py` 调 `common.vision` 的 `expect_template` / `expect_ocr` 判页面；`page.py` 用 `ctx.runtime.ctrl.click(...)` 落到 `common.device.DeviceService`。
7. `common.vision.screenshot` 内部同样经 `ctx.runtime.ctrl.screenshot()` 取帧。

终止收尾走另一条：`dispatch/executor.py` 的 `_navigate_to_home` 先 `get_session().clear_pages()`，再用 `NavigationService(context.request(), checkpoint=False)` 回主页，失败则退回 `ensure_ready` 重新初始化。

## 4. 边界速查

| 我要改…… | 去看 |
| --- | --- |
| 新增一个页面能被导航到 | [导航器](application/navigation/README.md) 的"新增一个页面"清单 + [控制器](application/controller/README.md) 的 checker 约定 |
| 某个按钮点不中 | 对应页面包的文档（入口：[控制器索引](application/controller/README.md)）里的 `page.py` 与模板约定 |
| 识别阈值、ROI、OCR | [识别能力](common/vision.md) |
| 截图、点击、模拟器 | [设备](common/device.md) |
| 日志通道、错误类型、YAML 读写 | [系统基础](common/system.md) |
| 任务怎么被调度、上下文怎么传 | `autowsgr/dispatch/`（不在本目录范围内，见源码 docstring） |

## 5. 目录与文档索引

```text
docs/AutoWSGR3.0/
├── README.md                  本篇：分层、依赖方向、主链路、索引
├── common/
│   ├── system.md              日志 / 错误 / 文件边界 / 枚举 / LogConfig
│   ├── device.md              ADB / Scrcpy / 输入 / 截图 / 模拟器生命周期
│   └── vision.md              ROI / 模板 / 像素 / OCR 与 expect_* 入口
└── application/
    ├── navigation/
    │   └── README.md          导航器一包一篇：页面模型、可达图、执行器、对外入口
    └── controller/
        ├── README.md          根包与公共契约、七个业务包总索引
        ├── home.md            home/
        ├── login.md           login/
        ├── mission.md         mission/
        ├── sidebar.md         sidebar/ + build / friend / intensify
        ├── backyard.md        backyard/ + academy / bath / canteen / rank_room
        ├── sortie.md          sortie/ + battle / battle_preparation（含 quick_maintenance、
        │                      ship_recognition、ship_pool）/ exercise
        └── event.md           event/ + stage_push
```

**common**（3 篇）

- [common/system.md](common/system.md) —— 全仓共用的日志、错误基类、受限文件读写与枚举基类。
- [common/device.md](common/device.md) —— 唯一允许直接操作设备的模块，上层通过 `ctx.runtime.ctrl` 使用它。
- [common/vision.md](common/vision.md) —— 唯一的识别能力出口，七个公开函数覆盖模板、像素、OCR 与截图。

**application/navigation**（1 篇）

- [navigation/README.md](application/navigation/README.md) —— 导航器整包：33 个 `PageName`、3 个识别域 / 17 个 checker / 4 页 9 标签 / 29 个起点 55 条边、BFS 算路与逐边执行、`NavigationService` 三个对外入口。

**application/controller**（8 篇 = 1 篇总览 + 7 个业务包）

- [controller/README.md](application/controller/README.md) —— 根包（`types.py` / `template.py`）、三类识别入口约定、页面控制器约定、维护清单。
- [home.md](application/controller/home.md) —— `home/`：主页四层与三个每日浮窗、浮窗记账。
- [login.md](application/controller/login.md) —— `login/`：登录页、区服选择、更新提示、加载与黑屏。
- [mission.md](application/controller/mission.md) —— `mission/`：任务页与领奖浮窗。
- [sidebar.md](application/controller/sidebar.md) —— `sidebar/`：一级菜单与二级菜单、建造（含委托旧流程的 build/destroy_ships）、好友、强化三标签。
- [backyard.md](application/controller/backyard.md) —— `backyard/`：后院主页与学院 / 浴室 / 食堂 / 军阶室四个二级页。
- [sortie.md](application/controller/sortie.md) —— `sortie/`：出征五标签、选章与翻图、四种准备页、补给修理面板、六槽舰队识别、船池、演习选对手。
- [event.md](application/controller/event.md) —— `event/`：活动入口与地图、难度与节点解析、推图浮窗。

每篇开头都有"源码"与"上级"两行，可以沿上级链走回本篇；同一个包里的子包（如 `sortie/` 下的 `battle_preparation/`）在同一篇里用二级标题分节。

## 6. 维护这份文档

- **目录增删即文档增删**：新增一个被独立维护的包目录，就新增一篇 md；删除目录就删除对应 md，不留空文档。
- **改公开入口必须同步**："调用入口与出口"里列的函数签名、返回值语义来自源码；签名变了文档同一提交内改。
- **不写计划**：文档只描述已经存在的代码。没实现的能力不写，实现被删了就连同描述一起删。
- **路径用相对路径互链**：各篇结尾的"索引"要能互相点到，形成闭环。

## 7. 当前跨层契约的实际状态

以下是核对源码时确认的事实，不是计划：

- 新导航器的真实调用方目前只有 `dispatch`：`dispatch/startup.py` 与 `dispatch/executor.py`。`business` 与 `server/routes/game.py` 里的 `goto_page` / `goto_bath_from_*` 在 `application/navigation` 中并不存在，这些链路 import 即失败。
- `autowsgr/common/types.py` 不存在，但 `business`、`application/vision`、`application/combat`、`dispatch/legacy_scheduler`、`server/serializers` 仍从它导入 `PageName`、`ShipType`、`Formation` 等名字。
- 控制器各 `page.py` 的固定落点仍取自旧框架 `autowsgr.application.ui.controller.*` 的 `constants`；`navigation/registry.py:71` 仍从旧框架导入 `EventPage`。
- `application/runtime/launcher.py` 仍引用 `common.device` 的 `AndroidController` / `ScrcpyController`（当前该包入口只导出 `service` 子模块，实际公开门面是 `common.device.service.DeviceService`），并按旧签名调用 `setup_logger(...)`。
- 旧框架 `autowsgr/application/ui/` 与 `autowsgr/application/vision/` 仍在仓内，新模块不应再依赖它们。

各篇文档在自己的"怎么维护"里记录对应边界内的注意事项。
