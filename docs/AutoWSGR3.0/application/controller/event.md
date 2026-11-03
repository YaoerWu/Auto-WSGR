# controller/event —— 活动与推图（stage_push）

源码：`autowsgr/application/controller/event/`
上级：[controller 总览](README.md)

## 1. 模块定位

活动玩法。目前只有**推图**（`stage_push`）一种：活动入口卡片 → 活动地图页 → 出征准备浮窗。活动有普通/困难两种难度，每难度 6 个节点。

**本包没有 `page.py`**——所有点击动作按事件类型写在导航层（`registry.py` 的具名动作，如 `_event_map_to_overlay`），这里只做识别与关卡解析。

## 2. 目录

```text
event/
├── __init__.py      __all__ = ['stage_push']，只把子包暴露出去
└── stage_push/
    ├── checker.py   页面/浮窗判定、难度与节点解析、落点读取、等待
    └── __init__.py  导出 3 个类型 + 12 个公开函数
```

## 3. 识别入口

```python
# 页面与浮窗
check_event_entry(ctx, *, event_type: str) -> bool
check_event_map_page(ctx, *, absent=False, ..., event_type: str | None = None) -> bool
check_event_sortie_prepare(ctx, *, ..., event_type: str | None = None,
                           stage: str | None = None) -> bool
read_sortie_overlay(ctx, *, absent=False, ...) -> bool

# 现场事实（从任务绑定读，不读画面）
read_event_type(ctx) -> str    # ctx.read_event_type()；未绑定抛 NavigationError
read_event_stage(ctx) -> str   # ctx.read_event_stage()；未绑定抛 NavigationError
read_event_map_state(ctx, *, ..., event_type: str | None = None) -> EventMapState
read_stage_title_texts(ctx) -> list[str]

# 落点
read_mode_button_center(ctx) -> tuple[float, float] | None
read_sortie_prepare_center(ctx) -> tuple[float, float] | None

# 等待
wait_event_mode(ctx, *, event_type: str, mode: EventMode, ...) -> bool
```

`check_event_map_page` 的判据是"模式按钮命中 **或**（地图标题为普通名且没有浮窗）"——浮窗会压暗整页让两张按钮模板一起失效，所以按钮还亮着同时说明页面干净。

## 4. 关卡与难度

```python
class EventMode(StrEnum):
    NORMAL = 'normal'
    HARD = 'hard'

@dataclass(frozen=True, slots=True)
class EventStage:
    difficulty: EventMode
    node: int                  # 1-6（_NODE_COUNT = 6）

@dataclass(frozen=True, slots=True)
class EventMapState:
    on_clean_map: bool
    button_mode: EventMode | None
    title_mode: EventMode | None
    current_mode: EventMode | None
```

- `parse_stage(stage)`：解析关卡串，新格式 `EX1–EX12`，兼容旧 `E1–E6` / `H1–H6`（迁移期双格式）。
- `calculate_current_mode(button_mode, title_mode)`：按钮与标题两个来源投票，只有一个来源时取它，冲突返回 `None`。
- `is_stage_title_matched(title_texts, *, node, hard)`：标题文本里是否出现目标节点。

## 5. 维护

- **`event_type` 是"选对 checker"的校验，不是页面事实**：`check_event_*` / `read_event_map_state` / `wait_event_mode` 收到它时调 `_require_activity`，与本期活动不一致直接抛 `ValueError`；导航器定位页面时传 `None` 跳过校验。
- **任务绑定走 `ctx`**：`read_event_type` / `read_event_stage` 读任务事实，没绑定时抛 `NavigationError('活动导航需要任务绑定 event_type')`。
- **改关卡编号规则**只改 `parse_stage` 与 `_NODE_COUNT`；旧格式兼容属迁移代码，达到删除条件时整段移除。
- **活动类型不写死**：入口普遍有 `event_type: str | None` 参数，由业务层传入（如 `'stage_push'`），本包不枚举活动。
- **本包没有 click**：新增点击要放到 `registry.py` 的具名动作里，否则导航表没有落点。
- 难度判定依赖"按钮 + 标题"两个来源，只读一个会在切换动画中间误判。
