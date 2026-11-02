# 待办清单

状态：**进行中**（2026-10-30 建立）。

所属任务：`codex/20260913-shiinaskuya-upgrade-7b3e`（worktree `AutoWSGR/.worktrees/ShiinaSkuya-upgrade`）

本文件只记「已经明确、但不在当前切片里做」的事项。每条给出：现在什么状态、为什么要做、
动手时改哪里、做完怎么算完。动手前先看条目里的前置条件，缺前置就先把前置补上。

| # | 事项 | 归属 | 状态 | 前置 |
| --- | --- | --- | --- | --- |
| 1 | 演习对手挑战状态上下文 | 导航器 + 业务层 | 未开始 | 任务书 P4 实机跑通 |
| 2 | `controller/operations` 全量搬迁 | UI 控制器 | 部分完成 | 无 |
| 3 | 准备页返回按钮换模板中心 | 导航器 + 素材 | 等素材 | 用户补返回按钮模板与 ROI |
| 4 | `battle_page` 残留清理与两个旧消费者迁移 | 导航器 + 运行时 | 未开始 | 无 |
| 5 | fleet_recognition 改能力层 | 编队控制器 | 未开始 | 另一 agent 的 formation 改动落地 |
| 6 | fleet_adjustment 迁 `ContextHandle` | 编队控制器 | 未开始 | 同 5 |
| 7 | 获得船整屏动画挡住主页 | 导航器 | 未开始 | 无 |
| 8 | 准备页「开始出征」按钮接战斗 | 控制器 + 战斗域 | 未开始 | 战斗模块重写 |

## 1. 演习对手挑战状态上下文

明细单独一份：[`[todo]演习对手挑战状态上下文.md`](<./[todo]演习对手挑战状态上下文.md>)。

一句话：演习页「哪几个对手还打得过」现在每局都要重新认一遍画面，需要一份跨步骤的上下文，
业务层每打一场就地更新，刷新时刻和冷启动时重建。

## 2. `controller/operations` 全量搬迁

**现在什么状态**：`autowsgr/application/ui/controller/` 下同时存在两套布局——
顶层直属子包（`backyard` / `fleet` / `home` / `login` / `sidebar` / `sortie`）和
`operations/` 里的旧布局（`mission_page` / `sortie_page`）。导航器 checker 已经全部按
`navigation/checker/<模块>/<子模块>/` 摆好，控制器要对齐，不再有 `operations` 这一层。

**本次已搬的部分**：`operations/sortie/battle_preparation/` → `controller/sortie/battle_preparation/`；
新建 `controller/sortie/exercise/`；删 `operations/sortie_page/exercise_page/`。

**还要搬的部分**：

| 现路径 | 目标路径 |
| --- | --- |
| `controller/operations/mission_page/` | `controller/mission/` |
| `controller/operations/sortie_page/main_page/` | `controller/sortie/main_page/` |
| `controller/operations/sortie_page/battle_page/` | `controller/sortie/battle/`（先做第 4 条） |
| `controller/operations/sortie_page/campaign_page/` | `controller/sortie/campaign/` |
| `controller/operations/sortie_page/decisive_page/` | `controller/sortie/decisive/` |
| `controller/operations/sortie_page/expedition_page/` | `controller/sortie/expedition/` |

**牵连范围**：`controller.operations` 全仓约 69 个文件、177 处引用（源码 40+、`testing/ui` 20+、
`tools/` 3、`docs/` 4、`business/` 6）。搬完要一起改 import，不能留别名包。

**为什么不能留别名**：worktree 规则 §4 明确禁止为新旧两套实现留兼容适配层；别名包就是
最典型的适配层，会让「到底哪套是现行实现」永远说不清。

**怎么算完**：`controller/` 下不再有 `operations/`；全仓 grep 不到 `controller.operations`；
`pytest testing/application testing/ui` 全绿；`ruff check` 干净。

## 3. 准备页返回按钮换模板中心

**现在什么状态**：`controller/sortie/battle_preparation/page.py` 的 `go_back()` 用历史坐标
`CLICK_BACK = (0.0313, 0.0528)`。这四个准备页（出征 / 决战 / 演习 / 战役）共用同一个左上返回圆环，
场景一旦换分辨率或 UI 微调就会点空。

**要做的事**：

1. 用户补一张返回按钮模板 + 配死 ROI（比模板大 1px，按素材目录既有的约定）；
2. 入库到 `resources/image/application/ui/navigation/checker/sortie/battle_preparation/`；
3. `checker/sortie/battle_preparation/checker.py` 加 `read_back_center(ctx) -> tuple[float, float] | None`
   （`expect_template_center(..., attempts=1)`，照 `backyard.read_academy_entry_center` 的写法）；
4. 边动作改成 `BattlePreparationPage(ctx).go_back(battle_preparation.read_back_center(ctx))`，
   控制器内 `position if position is not None else CLICK_BACK`。

**怎么算完**：四个准备页上 `read_back_center` 都稳定返回非空；`go_back` 的兜底坐标被模板中心覆盖；
一条 focused 单测证明「拿不到中心时仍然点兜底坐标」。

## 4. `battle_page` 残留清理与两个旧消费者迁移

**现在什么状态**：`controller/operations/sortie_page/battle_page/` 里 `recognition.py` 和
`constants.py` 已经是死文件——`__init__.py` 只导出 `BattlePage`，这两个文件只有彼此互相引用。
`recognition.py` 顶部还 `from autowsgr.common.vision import PixelChecker`，这个符号早已删除，
一旦有人 import 就直接 `ImportError`。

**两个还在引用它的旧消费者**（都本来就 import 就炸，与本切片无关）：

| 文件 | 现状 |
| --- | --- |
| `autowsgr/application/runtime/context/game_context.py:271` | `from ...battle_page import BattlePage, recognition`，上游 `common.types` 已不存在 |
| `autowsgr/business/combat/bettle/normal_fight.py:16` | 同上，且 `CombatPlan` 也不存在 |

**要做的事**：

1. 把两个旧消费者里对 `recognition` 的使用，改成走 `common.vision`。注意新 checker 里现有的
   `_read_chapter_state` / `_read_map_identity` 是私有函数（被 `ensure_chapter` 使用），
   需要时才提升为公开入口；`_read_loot_and_ship_count`（战利品与舰船数）在新框架里**还没有对应实现**，
   要按 `expect_ocr` 重写一份；
2. 删 `battle_page/recognition.py` 与 `battle_page/constants.py`，`constants.py` 里还活着的点击坐标
   并入 `page.py`；
3. `battle_page/` 按第 2 条搬到 `controller/sortie/battle/`。

**注意**：`_read_loot_and_ship_count` 的旧实现在 `battle_page/recognition.py:417`，
返回战斗结算里的战利品与舰船数。迁移时不要照抄旧实现——它依赖的 `OCREngine` 已经不存在，
要按 `expect_ocr` 的 `ROI` + `allowlist` 重写，并用真实结算截图验一遍。

## 5. fleet_recognition 改能力层

**现在什么状态**：`controller/fleet/formation/fleet_recognition/` 仍在用旧框架的识别入口
（`PixelChecker` / `OCREngine` / 旧 `application.vision` 校准数据），还不是 `common.vision` 的能力层。
`controller/fleet/main_page/page.py:29` 也同样引用了 `PixelChecker`。

**为什么现在不做**：`controller/fleet/formation/*` 当前有另一条并发改动（`fleet_adjustment`、
`ship_selection`、`workflow.py`，以及未跟踪的 `application/ui/ships/`），同一个目录两个 agent 同时改会打架。

**怎么算完**：`controller/fleet/` 下 grep 不到 `PixelChecker` / `OCREngine` / `application.vision`；
识别入口全部走 `expect_template` / `expect_ocr` / `expect_pixels`；换船相关单测全绿。

## 6. fleet_adjustment 迁 `ContextHandle`

**现在什么状态**：`controller/fleet/formation/fleet_adjustment/` 的 `campaign.py` / `workflow.py`
还直接拿 `UIContext` / `GameContext` 这类旧上下文对象，不符合 dispatch-context 规范
（新模块只接收 `autowsgr.dispatch.context.ContextHandle`）。

**为什么现在不做**：同第 5 条，目录正在被另一条改动占用。

**怎么算完**：`fleet_adjustment` 全部入口收 `ContextHandle`，通过 `ctx.runtime` 取服务、
通过句柄方法读写任务事实；不再出现 `UIContext` / `GameContext` 参数。


## 7. 获得船整屏动画挡住主页

**现在什么状态**：每日奖励有概率开出舰船，出船时会播一整屏的获得动画，把主页模板整个挡住。此时
`home.read_home_layer` 七个模板一个都不命中，`detect_clean_layers` 返回空元组，`_current_page`
抛 `NavigationError('无法识别当前页面')`。实测在 2026-10-30 的 nav_chain 首跳复现，链路当场断掉。

**为什么当时不处理**：低概率事件，用户手动关掉了那个画面后链路恢复；本条先记下来，不在当前切片做。

**影响面**：任何「冷启动 / 栈空时正好在出船动画上」的路径都会失败——导航器所有调用方的第一条
`navigate_to` 都可能中招。

**动手时改哪里**：

1. 需要一张能认出「获得船动画」的模板（或一个稳定的像素点），先确认它和其他页面的误命中率；
2. 认出后属于哪一类：如果动画能点任意位置关闭，可以做成一条「清障」处理；如果不能关，就得等它播完
   （或加进 `_OVERLAY_PAGES` 当浮窗，走清浮窗链路）；
3. `detect_clean_layers` 现在只处理「层非空但顶层是浮窗」，空元组直接抛错；加这一条时要先决定
   空元组到底是「再等一帧」还是「真的不认识当前页」。

**怎么算完**：实机在出船动画上冷启动，`navigate_to(HOME)` 能自己走到干净主页；一条 focused 单测
覆盖「扫到获得船动画 → 清掉 → 重扫落回主页」。

**注意**：不要为了这一条把 `detect_clean_layers` 改成无限重试；`_current_page` 的抛错是导航器唯一
的「我不认识现在在哪」出口，改了会让真正的不认识也变成静默重试。

## 8. 准备页「开始出征」按钮接战斗

**现在什么状态**：出征准备页右下角「开始出征」按钮在四种准备页上都存在
（OCR bbox (1050,653)–(1185,692)），点击即进入战斗。战斗模块（`business/combat`、
`controller/sortie/battle/`）尚未重写，点了没有后续，所以
`controller/sortie/battle_preparation/page.py` **目前不提供 `start_battle`**。

**为什么现在不做**：见 `[任务书]出征准备页重写.md` §4.5——按钮本身只是「单次点击」，
缺的是点击之后的整条战斗链路，不属于准备页切片的范围。

**动手时改哪里**：

1. `controller/sortie/battle_preparation/page.py` 加 `start_battle(position=None)`，
   落点 `position or _CLICK_START_BATTLE`，候选兜底坐标 (0.8500, 0.9348)（旧 `CLICK_START_BATTLE`，
   与 OCR 中心 (1117,672) → (0.8727, 0.9333) 相差约 28px，仍在按钮内，落地前用模板中心重新标定）；
2. `checker/sortie/battle_preparation/checker.py` 加 `read_start_battle_center(ctx)`；
3. 导航器加「准备页 → 战斗」边的目标页（`PageName` 需要一个战斗页成员），或者做成业务流程第一步；
4. 点击前应确认编队合法（1 号位非空、战役/决战不左移），校验入口见
   `docs/features/[知识]战斗域游戏结构 — 征战页与编队准备页通用规则.md`。

**怎么算完**：四种准备页上点击都能进入战斗；编队非法时点击前就报错，不把空编队送进去；
一条 focused 单测覆盖「拿不到模板中心时点兜底坐标」。
