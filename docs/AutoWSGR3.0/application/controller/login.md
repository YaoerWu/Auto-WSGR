# controller/login —— 登录、区服选择与启动态

源码：`autowsgr/application/controller/login/`
上级：[controller 总览](README.md)

## 1. 模块定位

游戏启动到进入主页之间的全部页面：服务器选择、登录页、更新提示、加载中、黑屏。启动序列由 `NavigationService.navigate_to_login` 驱动，本包只提供每帧判定与单击。

## 2. 目录与文件

| 文件 | 内容 |
| --- | --- |
| `checker.py` | 5 个 `check_*` + 4 个 `read_*` + `get_server_index` |
| `page.py` | `LoginPage` |
| `__init__.py` | 导出 `LoginPage` 与所有公开 checker |

## 3. 识别入口

```python
# 启动瞬态（默认只探一次）
check_black_screen(ctx, *, absent=False, attempts=1, interval_seconds=0.5) -> bool
check_update_prompt(ctx, *, absent=False, attempts=1, interval_seconds=0.5) -> bool
check_loading(ctx, *, absent=False, attempts=1, interval_seconds=0.5) -> bool

# 页面确认（默认 attempts 更大，用于到达确认）
check_login_page(ctx, *, attempts=..., ...) -> bool
check_server_select(ctx, *, attempts=..., ...) -> bool

# 区服定位
get_server_index(name: str) -> int                    # 纯函数：名字 → 序号
read_server_position(ctx, name: str) -> int | None    # 画面里该区服的实际序号
read_server_index(ctx, name: str) -> int              # 读当前高亮序号

# 落点
read_enter_button_center(ctx) -> tuple[float, float] | None
read_switch_entry_center(ctx) -> tuple[float, float] | None
```

## 4. 页面控制器

```python
class LoginPage:
    def click_enter_game(self, position: tuple[float, float] | None = None) -> None: ...
    def click_switch_entry(self, position: tuple[float, float] | None = None) -> None: ...
    def click_server(self, position: int) -> None: ...   # 点第 position 个区服
```

## 5. 维护

- **三个瞬态 checker 的 `absent=True` 语义与页面确认不同**：它们默认 `attempts=1`，用于"还在加载吗"的轮询，不是到达确认。
- `get_server_index` 是纯函数（名字 → 第几个），`read_server_position` 才读画面；两者不要混用。
- **更新提示必须人工兜底**：命中后由 `NavigationService` 抛 `ManualUpdateRequiredError('检测到游戏更新，需要人工处理')`，不自动跳过。
- 启动超时（`_LOGIN_PAGE_ATTEMPTS = 60`）在 service 层，不在本包；改等待时长改那边。
