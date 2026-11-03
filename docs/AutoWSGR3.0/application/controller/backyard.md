# controller/backyard —— 后院与四个二级页

源码：`autowsgr/application/controller/backyard/`
上级：[controller 总览](README.md)

## 1. 模块定位

主页 → 后院。后院主页本身只负责"确认在后院"与"四个二级页入口在哪、点进去"；学院、浴室、食堂、军阶室各是独立子包，负责自己的到达确认（军阶室还多一步进技能列表）。

## 2. 目录

```text
backyard/
├── checker.py        后院主页确认 + 四个入口落点
├── page.py           BackyardTarget、BackyardPage
├── academy/          学院：只确认到达
├── bath/             浴室：只确认到达
├── canteen/          食堂：只确认到达
└── rank_room/        军阶室：确认到达 + 进技能列表
```

## 3. 识别入口

```python
# 后院主页
check_backyard_page(ctx, *, absent=False, attempts=..., interval_seconds=...) -> bool

read_canteen_entry_center(ctx) -> tuple[float, float] | None
read_academy_entry_center(ctx) -> tuple[float, float] | None
read_rank_room_entry_center(ctx) -> tuple[float, float] | None
read_bath_entry_center(ctx) -> tuple[float, float] | None

# 子包
check_academy_page(ctx, *, absent=False, ...) -> bool
check_bath_page(ctx, *, absent=False, ...) -> bool
check_canteen_page(ctx, *, absent=False, ...) -> bool
check_rank_room_page(ctx, *, absent=False, ...) -> bool
```

四个落点函数各做一次模板匹配，命中返回中心，未命中返回 `None`。

## 4. 页面控制器

```python
class BackyardTarget(enum.Enum):
    CANTEEN = '餐厅'
    ACADEMY = '学院'
    RANK_ROOM = '军阶室'
    BATH = '浴室'
    # 属性 page_name -> PageName

class BackyardPage:
    def go_to(self, target: BackyardTarget, position: tuple[float, float] | None = None) -> None: ...
    def go_back(self) -> None: ...   # 点退回按钮，回上一级
    def go_home(self) -> None: ...   # 点二级页通用回首页按钮，直接回主页面

class RankRoomPage:                 # rank_room 子包
    def go_to_skill_list(self) -> None: ...   # 进军阶室技能列表三级页
```

## 5. 子包一览

| 子包 | checker | 页面控制器 | 说明 |
| --- | --- | --- | --- |
| `academy/` | `check_academy_page` | `AcademyPage`（只有构造函数） | 学院只做到达确认，无点击 |
| `bath/` | `check_bath_page` | `BathPage`（只有构造函数） | 浴室只做到达确认；泡澡等操作未迁入 |
| `canteen/` | `check_canteen_page` | `CanteenPage`（只有构造函数） | 食堂只做到达确认；请客吃饭属 business |
| `rank_room/` | `check_rank_room_page` | `RankRoomPage.go_to_skill_list` | 三级页 `RANK_SKILL_LIST` 没有 checker |

## 6. 维护

- **加一个二级页入口**：枚举加成员、页面映射表加一项、checker 加 `read_*_entry_center`、`navigation/registry.py` 加边。
- **不要把二级页识别塞进本包**：本包只知道"入口在哪"，页面确认在各自子包。
- **回首页有两条路**：逐级 `go_back`，或 `go_home` 一步回主页；需要清空导航栈时用后者。
- **三级页无 checker**：`RANK_SKILL_LIST` 不在导航表，到达时跳过确认；要补确认需在 `registry._PAGE_CHECKERS` 登记。
- 页内新增操作时，先给子包 `page.py` 加单次点击方法，落点参数与其它包一致（`position` 优先、`None` 回退静态坐标）。
