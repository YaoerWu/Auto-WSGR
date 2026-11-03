# controller/home —— 主页与每日浮窗

源码：`autowsgr/application/controller/home/`
上级：[controller 总览](README.md)

## 1. 模块定位

主页是导航的枢纽：五个入口（出征/任务/侧边栏/后院/活动）都在这里。主页还会弹每日浮窗（新闻确认、每日奖励、奖励确认），挡住任何一个入口按钮，所以"主页到位"必须是"浮窗清完"。

**负责**：主页族四层的识别、浮窗确认与记账、五个入口与三个浮窗按钮的单击。
**不负责**：浮窗清除的顺序（在导航边里编排）、每日奖励的业务判定（在 business）。

## 2. 目录与文件

| 文件 | 内容 |
| --- | --- |
| `checker.py` | 层读取、浮窗识别、浮窗记账、落点读取 |
| `page.py` | `Target` 枚举、`HomePage` |
| `__init__.py` | 导出 `HomeNewsOverlay`、`HomePage`、`Target` 及全部 `check_*` / `read_*` / `popups_*` |

## 3. 识别入口

```python
read_home_layer(ctx, *, attempts=..., interval_seconds=...) -> tuple[PageName, ...]
popups_all_settled() -> bool          # 读 dispatch 事实，不读画面
mark_popups_settled(ctx) -> None      # 清完记账，后续到达不再重复清

read_news_overlay(ctx, ...) -> HomeNewsOverlay   # (matched, checked)
check_news_checked(ctx, ...) -> bool
check_home_reward_overlay(ctx, ...) -> bool
check_home_reward_confirm(ctx, ...) -> bool

read_news_checkbox_center(ctx) -> tuple[float, float] | None
read_reward_claim_center(ctx) -> tuple[float, float] | None
read_reward_confirm_center(ctx) -> tuple[float, float] | None
```

`read_home_layer` 是**域读取**：一次截图读出画面里所有成立的主页族页面（`HOME` 与三个浮窗），**由深到浅**排列，供 `navigation` 的 `probe_domains` 取最深那个作为当前页。

事实模型：

```python
@dataclass(frozen=True, slots=True)
class HomeNewsOverlay:
    matched: bool             # 新闻浮窗是否存在
    checked: bool | None      # 勾选框是否已勾选；未匹配时为 None
```

## 4. 页面控制器

```python
class Target(enum.Enum):
    SORTIE = '出征'      # page_name -> SORTIE_MAP
    TASK = '任务'        # page_name -> MISSION
    SIDEBAR = '侧边栏'   # page_name -> SIDEBAR
    BACKYARD = '后院'    # page_name -> BACKYARD
    EVENT = '活动'       # page_name -> EVENT_MAP

class HomePage:
    def go_to(self, target: Target) -> None: ...
    def click_news_checkbox(self, position: tuple[float, float] | None = None) -> None: ...
    def click_news_close(self) -> None: ...
    def click_reward_claim(self, position: tuple[float, float] | None = None) -> None: ...
    def click_reward_confirm(self, position: tuple[float, float] | None = None) -> None: ...
```

## 5. 维护

- **浮窗记账是会话级事实**：`mark_popups_settled` 写进 dispatch，`popups_all_settled` 读它；导航的 `on_arrival` 在到达 `HOME` 时调用。新增浮窗要同步更新记账判定，否则新浮窗会被漏清。
- **浮窗清除动作在导航边**：`_close_daily_news`、`_claim_daily_reward`、`_confirm_daily_reward` 属于 `navigation/registry.py`，本包只提供识别与单击。
- **`_POPUP_SETTLE_SECONDS = 2.0`**：浮窗有出场动画，识别前要等，别调小。
- 主页族共 4 个页面；新增浮窗必须同时进 `navigation/types.py` 的 `PageName` 与 `registry.py` 的域表浮窗列。
