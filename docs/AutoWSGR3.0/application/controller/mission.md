# controller/mission —— 任务页与领奖浮窗

源码：`autowsgr/application/controller/mission/`
上级：[controller 总览](README.md)

## 1. 模块定位

主页 → 任务页。任务页会弹领奖确认浮窗。任务奖励与每日奖励是两条独立链路（每日奖励在 [home.md](home.md)）。

## 2. 目录与文件

| 文件 | 内容 |
| --- | --- |
| `checker.py` | `check_mission_page`、`check_mission_reward_confirm`、`check_claim_all_button` |
| `page.py` | `MissionPage` |
| `__init__.py` | 导出 `MissionPage` 与三个 checker |

## 3. 识别入口

```python
check_mission_page(ctx, *, attempts=..., ...) -> bool
check_mission_reward_confirm(ctx, *, attempts=..., ...) -> bool
check_claim_all_button(ctx, *, attempts=1, ...) -> bool   # 一键领取按钮是否还在
```

## 4. 页面控制器

```python
class MissionPage:
    def click_claim_all(self) -> None: ...
    def click_reward_confirm(self) -> None: ...
    def go_back(self) -> None: ...
```

## 5. 维护

- **一键领取要点到"按钮消失"**：`check_claim_all_button` 的存在性就是循环终止条件（导航边 `_claim_all_mission_rewards` 用它，`_CLAIM_CONFIRM_ATTEMPTS = 8`）。
- `check_claim_all_button` 默认 `attempts=1`，是"探一次"，不要当到达确认用。
- 入口在 `HomePage.go_to(Target.TASK)`，返回用 `MissionPage.go_back`；不要在任务包里直接回主页。
