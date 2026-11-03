# application/controller —— 页面识别与单击

源码：`autowsgr/application/controller/`
上级：[架构总览](../../README.md) · 同级：[navigation](../navigation/README.md)

## 1. 模块定位

导航器的**眼睛和手指**：每个业务包回答两件事——"现在是不是这一页"（`checker.py`），"这一页的按钮在哪、点一下"（`page.py`）。它不做流程编排，不明白"为什么要来这一页"。

**不负责**：

- 不决定去哪一页（路径计算归 `application.navigation`）；
- 不做多步业务流程（建造/解装的完整流程仍委托旧框架 workflow，见 [sidebar.md](sidebar.md)）；
- 不持有任务事实的写权限，只读页面、只点一次。

## 2. 目录与文件

```text
autowsgr/application/controller/
├── __init__.py    只导出类型，__all__ = []
├── types.py       跨页面复用的业务枚举：ShipType（24 个舰种）
├── template.py    应用层模板加载器：UI_TEMPLATE_ROOT / load_ui_template
├── backyard/      后院主页 + academy / bath / canteen / rank_room 四个二级页
├── event/         活动检查器出口，只有 stage_push 一个子包
├── home/          主页与三个每日浮窗
├── login/         登录页、区服选择、更新提示、加载与黑屏
├── mission/       任务页与领奖浮窗
├── sidebar/       侧边栏 + build / friend / intensify 三个子页
└── sortie/        出征页 + battle / battle_preparation（含 quick_maintenance、
                   ship_recognition、ship_pool）/ exercise
```

**20 个业务包，每包一个 `checker.py`**；除 `event/stage_push` 外都有 `page.py`。没有独立页面的包（`event/`、`quick_maintenance/`）按目录归属并入一级包文档。

### 2.1 根包三个文件

| 文件 | 内容 |
| --- | --- |
| `types.py` | `ShipType`（24 个舰种的中文名，`__all__ = ['ShipType']`），供船池识别与 business 共用 |
| `template.py` | `UI_TEMPLATE_ROOT = 'application'`；`@cache load_ui_template(namespace, filename, *, name=None) -> Template`，路径 `f'{UI_TEMPLATE_ROOT}/{namespace}/{filename}'`，最终交给 `common.vision.adapters.template_matching.load_template` |
| `__init__.py` | 空导出，避免 controller 内部包被自动拉起 |

模板缓存在进程内不可失效：换图要重启进程。各包只写一层很薄的 `_load_template` 把 namespace 写死一次，不在调用方拼路径。

## 3. 依赖关系

```text
  navigation.registry ──取 checker、取动作──┐
  navigation.executor ──到达确认──┐          │
                                  ▼          ▼
                         ┌──────────────────────┐
                         │  controller/<包>/     │
                         │  checker.py page.py   │
                         └──────────────────────┘
                           │                 │
                template.py → common.vision    page.py → ctx.runtime.ctrl
                （模板/OCR/像素识别）           （common.device 截图与点击）
```

- **上层谁调它**：`navigation.registry` 把 checker 与动作登记进表；dispatch 按任务直接调用页面控制器。
- **它下层依赖谁**：`common.vision`（`expect_template` / `expect_ocr` / `expect_pixels` 及其 `_center` 变体）、`ctx.runtime.ctrl`（截图与点击）。
- 只有 `home/checker.py` 回读 `dispatch.session` 的每日浮窗记账，其余包不碰 dispatch 状态。

## 4. 三类识别入口

| 形态 | 签名约定 | 用途 |
| --- | --- | --- |
| 页面确认 | `check_<page>(ctx, *, absent=False, attempts=..., interval_seconds=...) -> bool` | 是不是这一页；`absent=True` 判"已经不在" |
| 层读取 | `read_<域>_layer(ctx, ...) -> tuple[PageName, ...]` | 一帧读出同框架下的多层，**由深到浅**；域探针用 |
| 落点读取 | `read_<控件>_center(ctx) -> tuple[float, float] | None` | 读到返回识别中心，读不到返回 `None`（调用方回退静态坐标） |

所有入口第一个参数都是 `ctx: ContextHandle`，识别规则与预期由调用方给，`ctx` 由 dispatch 统一注入。

### 4.1 事实模型

多次识别结果要一起传出去时，用 `@dataclass(frozen=True, slots=True)` 的冻结事实对象，不返回裸 dict：

| 包 | 事实类型 |
| --- | --- |
| home | `HomeNewsOverlay(matched, checked)` |
| event/stage_push | `EventMode`、`EventMapState`、`EventStage` |
| sortie/battle | `MapIdentity`、`ChapterSlot` |
| sortie/battle_preparation/ship_recognition | `ShipDamage`（四个识别入口返回六槽列表，不带聚合法） |
| sortie/exercise | `RivalShip(slot, ship_type, level)` |
| sortie/battle_preparation/ship_pool | `ShipListText(text, center)` |

## 5. 页面控制器约定

```python
class XxxPage:
    def __init__(self, ctx: ContextHandle) -> None: ...
    def go_to(self, target, position: tuple[float, float] | None = None) -> None: ...
    def go_back(self) -> None: ...
    def go_to_tab(self, tab: XxxTab) -> None: ...
    def click_xxx(self, position: tuple[float, float] | None = None) -> None: ...
```

- 落点优先用识别中心（`position`），`None` 时回退模块常量里的静态校准坐标；两条路写在同一函数里，不给调用方选。
- 标签用 `enum.Enum` 表达（`BackyardTarget`、`Target`、`SidebarTarget`、`SortieTab`、`BuildTab`、`IntensifyTab`），并提供 `page_name` 属性让导航器直接取 `PageName`。
- 一次调用只做一次点击；等待、重试、多步流程留给上层。

## 6. 包索引

| 文档 | 覆盖的包 |
| --- | --- |
| [home.md](home.md) | `home/`：主页四层与三个每日浮窗、浮窗记账 |
| [login.md](login.md) | `login/`：登录页、区服选择、更新提示、加载与黑屏 |
| [mission.md](mission.md) | `mission/`：任务页与领奖浮窗 |
| [sidebar.md](sidebar.md) | `sidebar/` 及子包 `build` / `friend` / `intensify` |
| [backyard.md](backyard.md) | `backyard/` 及子包 `academy` / `bath` / `canteen` / `rank_room` |
| [sortie.md](sortie.md) | `sortie/` 及子包 `battle` / `battle_preparation`（含 `quick_maintenance`、`ship_recognition`、`ship_pool`）/ `exercise` |
| [event.md](event.md) | `event/` 及子包 `stage_push` |

## 7. 怎么维护

1. **新增一个页面**：建 `<页面>/checker.py` + `page.py` + `__init__.py`（`__all__` 只导出稳定入口）→ `navigation/types.py` 加 `PageName` → `navigation/registry.py` 登记 checker 与边。
2. **新增一个 checker**：函数名 `check_<page>`，签名必须与 registry 约定一致（`absent` 关键字、`attempts`、`interval_seconds`），否则到达确认会 TypeError。
3. **模板**：一律 `load_ui_template(namespace, filename)`，namespace 从 `application` 起算（如 `controller/home`）。
4. **坐标**：识别中心优先、静态坐标兜底；静态值集中在模块顶部常量区，并注明校准基准（1280x720）。
5. **不要反向依赖**：controller 不 import navigation 的实现模块，只 import `navigation.types` 的 `PageName`。

## 8. 已知遗留（只报告，未改）

- 14 个 `page.py` 的静态坐标仍取自旧 `autowsgr.application.ui.controller.*.constants`（共 16 处旧框架 import，含 `sidebar/build/page.py` 第 87、124 行委托旧 workflow）。
- `controller/__init__.py` 的 docstring 仍写 `application.ui.controller`，`event/__init__.py` 注释仍提"普通推图 normal"（实际只有 `stage_push`）。
