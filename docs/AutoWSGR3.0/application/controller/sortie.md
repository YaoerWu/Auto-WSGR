# controller/sortie —— 出征、作战与出战准备

源码：`autowsgr/application/controller/sortie/`
上级：[controller 总览](README.md)

## 1. 模块定位

主页 → 出征。出征页是第二个多层枢纽：同一个画面框架下挂着出征/演习/远征/战役/决战五个标签页。本包提供五标签的**层读取**，子包覆盖普通出征选章、出战准备（含补给修理面板、舰队与船池识别）、演习选对手。

## 2. 目录

```text
sortie/
├── checker.py                    read_sortie_layer：一帧读出五个标签页
├── page.py                       SortieTab、SORTIE_TAB_LIST、SortiePage
├── battle/                       普通出征：选章、翻图、进图
├── battle_preparation/           四种准备页识别、舰队标签
│   ├── quick_maintenance/        自动补给 / 快速修理 / 全部修理面板
│   ├── ship_recognition/         六个槽位的舰船、等级、舰种、血条识别
│   ├── ship_pool/                船池列表、搜索框、选船与拆卸
│   └── tactical_support/         战术支援按钮与浮窗
└── exercise/                     演习：对手列表与对手浮窗
```

## 3. 出征页本体

```python
read_sortie_layer(ctx, *, attempts=..., interval_seconds=...) -> tuple[PageName, ...]
```

一次截图返回成立度最高的页面（`SORTIE_MAP` / `EXERCISE` / `EXPEDITION` / `CAMPAIGN` / `DECISIVE_BATTLE`），**由深到浅**；某标签不可达时宁可返回空也不返回错页。

```python
class SortieTab(enum.Enum):
    SORTIE = '出征'       # page_name -> SORTIE_MAP
    EXERCISE = '演习'     # page_name -> EXERCISE
    EXPEDITION = '远征'   # page_name -> EXPEDITION
    CAMPAIGN = '战役'     # page_name -> CAMPAIGN
    DECISIVE = '决战'     # page_name -> DECISIVE_BATTLE

SORTIE_TAB_LIST = tuple(SortieTab)   # 供导航按序枚举标签

class SortiePage:
    def go_to(self, tab: SortieTab, position: tuple[float, float] | None = None) -> None: ...
    def go_back(self) -> None: ...
```

五个标签在 `navigation/registry.py` 里是一个**域**：由 `read_sortie_layer` 一次性归属，域内唯一浮窗是 `EXERCISE_RIVAL_CONFIRM`（进入动作 `_exercise_to_rival_overlay` 在 registry）。

## 4. battle —— 普通出征选章与翻图

```python
ensure_chapter(ctx, *, chapter: int, map_id: int) -> None
```

保证"当前停在 chapter 章 map_id 图"。三种失败各自有明确异常：`ValueError`（章节号越界）、`NavigationError`（选章卡住）、`RuntimeError`（选节超限）。

```python
@dataclass(frozen=True, slots=True)
class MapIdentity:
    chapter: int; map_num: int; name: str; raw_text: str

@dataclass(frozen=True, slots=True)
class ChapterSlot:
    index: int; chapter: int; text: str; confidence: float

class BattlePage(SortiePage):
    def click_chapter_slot(self, index: int) -> None: ...
    def click_map_next(self) -> None: ...
    def click_map_prev(self) -> None: ...
    def click_enter_sortie(self) -> None: ...
```

判读要"读两次一致"：内部 `_read_stable_map_number` / `_judge_stable_map_number` 两次读数比对，翻页动画期间读数会抖，别改成单次读。章节标签与图名两套解析（`_parse_chapter_label` / `_parse_map_title`）不要合并。

## 5. battle_preparation —— 四种准备页

```python
read_battle_preparation_layer(ctx, *, attempts=..., interval_seconds=...) -> tuple[PageName, ...]
read_team_tab(ctx, *, attempts=..., interval_seconds=...) -> int | None   # 舰队标签序号，1 起

class BattlePreparationPage:
    def go_back(self) -> None: ...
    def click_team_tab(self, team: int) -> None: ...
```

普通出征、决战、演习、战役四种准备页共用一个画面框架，同属一个域、**没有浮窗**；新增第五种要同时加域表页面集合、`PageName` 与域 checker。舰队标签从 1 起（与槽位编号一致），实现内部要用数组下标时临时减一。

## 6. quick_maintenance —— 补给与快修面板

没有独立页面（无 `PageName`），只有 checker + 面板动作类。

```python
check_auto_supply_enabled(ctx) -> bool
check_quick_repair_active(ctx) -> bool
read_repair_tool_count(ctx) -> int | None      # OCR，allowlist '0123456789'

read_auto_supply_center(ctx) -> tuple[float, float] | None
read_quick_repair_center(ctx) -> tuple[float, float] | None
read_all_repair_center(ctx) -> tuple[float, float] | None

class QuickMaintenancePanel:
    def click_auto_supply(self, center=None) -> None: ...
    def click_quick_repair(self, center=None) -> None: ...
    def click_all_repair(self, center=None) -> None: ...
    # 私有 _resolve_center(center, fallback)：识别中心优先，否则静态坐标
```

`read_all_repair_center` 用 `min_matches=2`：必须同时匹配"页签 + 全部修理"两个模板才认，单模板命中率太高会误判。`read_repair_tool_count` 的 OCR allowlist 只能是 `0123456789`。

## 7. ship_recognition —— 六槽舰队识别

六个槽位（1-6）的舰名、舰种、等级与血条状态；换船流程读槽位、点开槽位进船池（见第 8 节）。

包内只有四个文件：`checker.py`（四个识别入口）、`constants.py`（ROI、参考色、血条签名与槽位落点）、`page.py`（`FleetSlotPage` 槽位点击与拖拽）、`__init__.py`。不设 `service.py`：只有一个识别域时，"按任务类型路由"是空转抽象；演习对手浮窗属于演习页，识别入口在 `exercise/checker.py`。

```python
read_ship_damage(ctx) -> list[ShipDamage | None]   # 六槽血条档位
read_ship_types(ctx) -> list[str | None]           # 六槽舰种 OCR 原文
read_ship_levels(ctx) -> list[str | None]          # 六槽等级 OCR 原文
read_ship_names(ctx) -> list[str | None]           # 六槽舰名 OCR 原文

class ShipDamage(StrEnum): ...            # 定义在 constants.py；满血 / 中伤 / 大破 / 空槽
class FleetSlotPage:
    def click_slot(self, slot: int) -> None: ...   # 越界抛 ValueError
    def drag_slot(self, source: int, target: int) -> None: ...   # 拖拽换位
```

四个入口各自截一帧，返回长度 6 的列表，下标 0 是画面最左槽位。三个文字入口只给 OCR 原文：不剥国籍括号、不匹配 `ShipType`、不解析等级，整区空白时该槽为 `None`；解析与舰名比对全在 `fleet_select/rules/ocr.py` 与 `fleet_select/operation/fleet_snapshot.py`。

校准数据全部集中在 `constants.py`，`checker.py` 与 `page.py` 只读不定义：`FLEET_SLOT_COUNT = 6`、`SHIP_NAME_ROIS` / `SHIP_TYPE_ROIS` / `SHIP_LEVEL_ROIS` 各 6 个 ROI、`BLOOD_BAR_PROBES` 6 个、血条颜色常量（`BLOOD_GREEN`、`BLOOD_YELLOW`、`BLOOD_RED_PREPARE`、`BLOOD_EMPTY`、`BLOOD_NO_SHIP`）、由颜色派生的 `BLOOD_STATES` 与 `BLOOD_SIGNATURES` 六条组合签名、`ShipDamage` 枚举，以及槽位点击落点 `CLICK_SHIP_SLOTS` 与拖拽时长 `DRAG_DURATION_SECONDS`。

所有归一化坐标保留四位小数；`ROI.to_absolute` 用 `int()` 截断，所以取值按「目标像素除以分辨率后向上取到四位」反算，保证裁切像素与注释标注的像素区间一致。血条容差沿用 `NUMPY_DEFAULT_PIXEL_TOLERANCE = 30.0`（文件内 TODO 说明）。文字形态规则（国籍括号正则、等级形近字映射、1-110 区间）不在这里，在 `fleet_select/rules/constants.py`。

## 8. ship_pool —— 船池列表与选船

```python
check_ship_pool_page(ctx, *, attempts=5, interval_seconds=1.0, absent=False) -> bool  # 四个特征模板命中任一
read_ship_pool_kind(ctx, *, attempts=1) -> ShipPoolKind | None  # 读一帧，判属于哪一类船池
check_search_input(ctx, *, attempts=5, interval_seconds=1.0) -> bool    # 3 条规则判软键盘唤起
read_ship_list_texts(ctx) -> tuple[ShipListText, ...]                   # ShipListText(text, center, region)

class ShipPoolKind(StrEnum):
    ACADEMY    # 学院船池
    STRENGTHEN # 强化船池
    DISMANTLE  # 拆解船池
    SORTIE     # 出征船池（含活动出征、演习）
    DECISIVE   # 决战船池

class ShipPoolPage:
    def click_search_box(self) -> None: ...
    def input_ship_name(self, name: str) -> None: ...
    def dismiss_keyboard(self) -> None: ...
    def click_card_at(self, center: tuple[float, float]) -> None: ...
    def click_remove_ship(self) -> None: ...
    def scroll_list_down(self) -> None: ...
    def go_back(self) -> None: ...
```

- `constants.py`：`SHIP_LIST_ROI = ROI(0.0, 0.12, 0.81875, 0.95)`（右界 1048px）、`SEARCH_INPUT_SIGNATURE('ship_pool_input', 3×PixelRule)`，以及四个分类模板名与各自的 1px 死区域（`QUICK_FORMATION_*`、`QUICK_SELECT_*`、`QUICK_STRENGTHEN_*`、`STAR_*`）。
- **分类靠模板而不是像素签名**：原来的 5 条像素规则在学院船池页只命中 4 条（`(1100,288)` 采到 `BGR=(81,58,37)`，距离 31 超容差），会把学院页判成不是船池。现在一帧匹配四个特征模板定类；四个模板的搜索区域只留 1px 余量，因为全图搜索时「快速编队」在出征、演习、决战三页互为 1.0000，「快速选择」对出征页也有 0.9387，阈值分不开。
- 列表文本坐标已经是整幅画面的归一化值：整帧识别后按 `SHIP_LIST_ROI` 的中心点筛选，不再需要加裁切偏移。
- 页内静态坐标：返回 `(0.0313, 0.0528)`、搜索框 `(0.7292, 0.0556)`、收起键盘 `(0.5208, 0.0926)`、拆卸 `(0.0865, 0.3093)`、滚动 `(0.4, 0.55) → (0.4, 0.30)`、时长 0.4 秒。
- **选船规则不在这里**：上层消费者是 `autowsgr/application/fleet_select/operation/ship_select.py`，本包只提供页面事实与单击。

## 9. tactical_support —— 战术支援按钮与浮窗

出征准备页右上角三格快捷按钮里的第二格：橙底点亮表示已开启，点开是「战术支援」浮窗，里面是开关按钮与今日剩余次数。决战、战役、演习三个准备页没有这个按钮（演习页快捷按钮整体右移一格，第二格是奖杯）。

```python
read_tactical_support_button_center(ctx, *, attempts=3, interval_seconds=0.5) -> tuple[float, float] | None
read_tactical_support(ctx, *, attempts=5, interval_seconds=0.5) -> TacticalSupportState | None

@dataclass(frozen=True, slots=True)
class TacticalSupportState:
    enabled: bool
    remaining: int | None
    total: int | None
    toggle_center: tuple[float, float] | None

class TacticalSupportPage:
    def click_support_button(self, center=None) -> None: ...
    def click_toggle_button(self, center=None) -> None: ...
```

- **只保留已开启态模板**（橙底 `TACTICAL_SUPPORT_ON_720P.png`，56×58）：匹配到就是已开启，匹配不到就是没开启，或者这个页面根本没有按钮。未开启态是蓝底圆环，留它会出事——演习页同一格是蓝底「预」字按钮，蓝底模板对演习页给 0.8491，只差 0.0009 就撞上 0.85 阈值。死区域 `TACTICAL_SUPPORT_ROI` 只容 ±1px 滑动，橙底模板最高误命中 0.6022。
- 浮窗开关按钮**两态底色完全相同**（RGB 33,141,244），模板分数 1.000 / 0.976 也分不开，只能 OCR：一次 `expect_ocr` 传两个区域，开关区读「未启用 / 已启用」，次数区读「本日剩余次数：10/10」后正则取已用与总数。
- 检测框是**相对识别区域**的坐标，`toggle_center` 已加上区域左上角偏移换算成整帧归一化值。
- 开关按钮落点 `(0.6617, 0.1653)`、浮窗开关落点 `(0.7906, 0.5028)` 都留了静态兜底，识别不到时按校准坐标点。
- **开启策略与流程编排不在这里**：业务层用两个读取入口判状态、调 `TacticalSupportPage` 点两下；关浮窗用 `BattlePreparationPage.click_team_tab(team)`——点已经激活的队伍标签不会切队，是安全关闭点。

## 10. exercise —— 演习页与对手浮窗

一屏四行对手，需要滑动翻页；进入某个对手弹详情浮窗（关闭/刷新/挑战/六个对手的舰种与等级）。

```python
read_overlay_close_center(ctx) -> tuple[float, float] | None
read_overlay_refresh_center(ctx) -> tuple[float, float] | None
read_overlay_challenge_center(ctx) -> tuple[float, float] | None

read_rival_ships(ctx) -> tuple[RivalShip, ...]   # 浮窗六槽的舰种与等级

@dataclass(frozen=True, slots=True)
class RivalShip:
    slot: int                                   # 1-6
    ship_type: ShipType | None = None
    level: int | None = None

class ExercisePage:
    def select_rival(self, rival_index: int) -> None: ...   # 0-3，屏内序号，不够先滑动
    def click_overlay_close(self, position=None) -> None: ...
    def click_overlay_refresh(self, position=None) -> None: ...
    def click_overlay_challenge(self, position=None) -> None: ...
```

常量：`OVERLAY_{CLOSE,REFRESH,CHALLENGE}_{ROI,TEMPLATE}`、`RIVAL_SHIP_{TYPE,LEVEL}_ROIS`（各 6 个，校准基准 1280x720）、`EXERCISE_RIVAL_SLOTS = 6`、`_RIVAL_CHALLENGE_POSITIONS`（四行挑战按钮 y 坐标）、`_SWIPE_TO_TOP` / `_SWIPE_TO_BOTTOM`、`_VISIBLE_SLOTS = 4`、`_SWIPE_SETTLE_SECONDS = 0.8`。

浮窗不展示对手舰名，`RivalShip` 因此没有 `name` 字段。舰种 ROI 只框住舰种两字、不含国籍括号，所以不做去括号处理；识别结果只接受 `ShipType` 枚举内的完整名称，`Other` 不参与匹配，错字一律返回 `None` 交给上层判。

## 11. 维护

- **加一个出征标签**：`SortieTab` 加成员 + `PageName` + `read_sortie_layer` 的域表 + `registry._TABS` + 域内页面集合，五处缺一不可。
- **`read_sortie_layer` 的等待参数别覆盖成 0**：标签切换有动画。
- **判读类逻辑（battle/ensure_chapter）不要外提私有函数**：它们依赖当前画面状态。
- **槽位与舰队编号一律 1 起**，只有实现内部取下标的瞬间减一。
- **新增船池/舰队操作先看消费者**：`application.fleet_select` 承担选船规则，controller 只做识别与单次点击。
