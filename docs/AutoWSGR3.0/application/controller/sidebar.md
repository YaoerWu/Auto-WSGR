# controller/sidebar —— 侧边栏与建造 / 好友 / 强化

源码：`autowsgr/application/controller/sidebar/`
上级：[controller 总览](README.md)

## 1. 模块定位

主页 → 侧边栏。侧边栏是中转层：建设与强化各有自己的二级菜单，好友直接是页面。侧边栏还会自己展开一排按钮，必须先"收成侧边栏态"才能点菜单。

## 2. 目录

```text
sidebar/
├── checker.py        一级菜单与两个二级菜单的确认
├── page.py           SidebarTarget、SidebarPage
├── build/            建造页：四个标签 + 建造/解体流程（委托旧框架）
├── friend/           好友页
└── intensify/        强化页：强化 / 改造 / 技能三个标签
```

四个包各有一个 `checker.py` 与 `page.py`。

## 3. 识别入口

```python
# 一级与二级菜单
check_sidebar_page(ctx, *, attempts=..., ...) -> bool
check_build_submenu(ctx, *, attempts=..., ...) -> bool
check_intensify_submenu(ctx, *, attempts=..., ...) -> bool

# build
check_build_page(ctx, *, attempts=..., ...) -> bool
check_dismantle_tab(ctx, *, attempts=..., ...) -> bool

# friend
check_friend_page(ctx, *, attempts=..., ...) -> bool

# intensify
check_intensify_page(ctx, *, attempts=..., ...) -> bool
check_remold_tab(ctx, *, attempts=..., ...) -> bool
check_skill_tab(ctx, *, attempts=..., ...) -> bool
```

## 4. 页面控制器

```python
class SidebarTarget(enum.Enum):
    BUILD = '建造'
    INTENSIFY = '强化'
    FRIEND = '好友'
    # 属性 page_name -> PageName（子菜单页或好友页）

class SidebarPage:
    def go_to(self, target: SidebarTarget) -> None: ...          # 点一级菜单项
    def go_to_submenu(self, target: SidebarTarget) -> None: ...  # 展开并进入二级菜单
    def go_back(self) -> None: ...                               # 点空白处收起侧边栏
```

## 5. 子包

### 5.1 build —— 建造页与解体

```python
class BuildTab(enum.Enum):
    BUILD = '建造'
    DESTROY = '解体'
    DEVELOP = '开发'
    DISCARD = '废弃'

class BuildPage:
    def build(self, *, build_count: int = 1, collect_completed: bool = True,
              build_type: str = 'ship', allow_fast_build: bool = False) -> int:  # 委托旧 workflow
    def destroy_ships(self, ship_types=None, *, remove_equipment: bool = True) -> None:  # 委托旧 workflow
    def go_to_tab(self, tab: BuildTab) -> None: ...
    def go_back(self) -> None: ...
```

这是本目录里**唯一仍携带旧框架业务流程**的包：`page.py` 第 87 行（`build`）与第 124 行（`destroy_ships`）直接 import 旧 `autowsgr.application.ui` 的 workflow，这里只保留页面识别与"去哪个标签"。`build` 返回本次实际建造/收取数量；`destroy_ships` 返回 `None`，失败靠内部异常。`DEVELOP` 与 `DISCARD` 目前只有标签枚举，没有操作入口。

### 5.2 friend —— 好友页

```python
class FriendPage:
    def go_to_tab(self) -> None: ...   # 点好友页内的标签
    def go_back(self) -> None: ...
```

checker 在导航表里登记为 `FRIEND`，但**没有 tab 表**——它的标签不参与路径选择。

### 5.3 intensify —— 强化页

```python
class IntensifyTab(enum.Enum):
    INTENSIFY = '强化'
    REMOLD = '改造'
    SKILL = '技能'

class IntensifyPage:
    def go_to_tab(self, tab: IntensifyTab) -> None: ...
    def go_back(self) -> None: ...
```

三个标签各有一帧可辨特征；导航靠 `_TABS` 里的 checker 判断是否已在目标标签（`_TAB_SETTLE_SECONDS = 2.0`、重试 2 次在 executor）。

## 6. 维护

- **收起是点空白处，不是点返回按钮**：`SidebarPage.go_back` 点画面空白，命中区域别乱改。
- **"收成侧边栏态"是导航边的职责**：`_settle_to_sidebar` 用 `_SIDEBAR_SETTLE_ATTEMPTS = 5`、`_SIDEBAR_SETTLE_INTERVAL_SECONDS = 0.4` 反复确认，本包不实现重试。
- **加一个侧边栏入口**：枚举加成员 + 映射表 + 需要时在 `registry.py` 加子菜单 checker 与边。
- **新增标签**要四处同步：枚举成员 + checker + `registry._TABS` 对应项 + `PageName`。
- **不要在 build 包里新增业务分支**：参数已透传给旧 workflow，再包一层会让迁移更难。
