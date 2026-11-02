# application-ui-navigation-checker 架构说明

版本：AutoWSGR-3.0 第 1 版
状态：生效
适用范围：`autowsgr/application/ui/navigation/checker`
实现基线：`codex/20260913-shiinaskuya-upgrade-7b3e`，2026-10-13（模板加载迁至 `application.ui.template`）

## 1. 模块定位

checker 是 **application 层导航器**的页面识别模块集合。它只回答「画面是不是这一页」，
为 [registry](<./registry.md>) 的确认表提供入口。

它明确不负责：点击与设备操作（属于 UI 控制器）、路由与路径执行（属于 [registry](<./registry.md>)
和 [executor](<./executor.md>)）、流程编排（属于 `service.py`）、
识别失败后的报错与恢复（由持有恢复策略的上层决定）。

所有权：

- 识别事实是返回值，不落库；截图事实由调用方传入的 `ContextHandle` 持有；
- 模板由 [application.ui.template](<../template.md>) 加载并缓存，本模块不持有缓存；
- 模板路径与识别区域由各子包 `checker.py` 的常量区持有，一个值只有一个定义源；
- 错误只使用入参校验的 `ValueError`，识别本身不产生业务错误。

## 2. 模块架构

### 2.1 目录树

~~~text
autowsgr/application/ui/navigation/checker/
├── __init__.py      # 包入口，只做归属声明，不导出实现
├── backyard/        # 后院主页与四个二级页
├── event/           # 活动玩法（本期：推图活动）
├── home/            # 主页与每日浮窗
├── login/           # 登录流程各画面
├── mission/         # 任务页与领奖浮窗
├── sidebar/         # 侧边栏、二级菜单与好友页
└── sortie/          # 出征页五个标签
    ├── checker.py          # 一帧判五个标签
    ├── battle/             # 出征页内导航：选章选节
    └── battle_preparation/ # 四种准备页一帧判层
~~~

### 2.2 子项职责

| 子项 | 文档 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- |
| `__init__.py` | 本表说明 | 包归属声明 | 导出实现、隐式初始化 |
| `backyard/` | 本文件 | 后院主页身份与四个入口中心；四个二级页身份 | 后院业务流程 |
| `event/` | 本文件 | 活动入口、地图难度、章节浮窗、活动绑定读取 | 活动业务执行 |
| `home/` | 本文件 | 主页身份与三个每日浮窗 | 主页业务操作 |
| `login/` | 本文件 | 登录页、区服选择页、启动三信号、区服定位 | 启动编排 |
| `mission/` | 本文件 | 任务页身份、领奖浮窗、全部领取按钮 | 任务业务 |
| `sidebar/` | 本文件 | 侧边栏、两个二级菜单、好友页、建造/强化页标签 | 侧边栏业务 |
| `sortie/` | 本文件 | 出征页五个标签的激活判定 | 出征业务 |
| `sortie/battle/` | 本文件 | 出征页内导航：从当前章走到第 N 章第 M 节 | 标签切换、进出页面 |
| `sortie/battle_preparation/` | 本文件 | 四种准备页一帧判层 | 准备页业务操作 |

**页面子包不单独建架构文档**，统一登记在本文件。理由：它们职责同构——同一套文件职责
（`constants` / `recognition` / `checker` / `__init__`）、同一套签名契约、同一套依赖方向，
差别只在校准数据与识别规则。逐个建文档会让「统一配置 / 错误约定 / 日志约定 / 公开出口 /
模块维护方法 / 验收门禁」这些公共章节重复多份，代码一改就要改多处。

子包的入口登记在本文件第 3 章「能力总览」；模板路径、ROI 和识别规则都看它的 `checker.py`。

### 2.3 子包内部结构

每个页面子包的识别入口都收在一个 `checker.py` 里，常量、事实读取和页面确认同文件：

~~~text
<页面>/
├── __init__.py      # 只导出稳定入口
└── checker.py       # 静态校准数据 + 识别入口 + 页面确认
~~~

原先拆开的 `constants.py` 和 `recognition.py` 已并入 `checker.py`：一个页面子包的校准数据、
识别逻辑和对外入口写在一起，减少无意义的跨文件跳转；文件内部仍按「常量 → 数据模型 →
识别入口 → 页面确认 → 私有辅助」分区。

子包装不装得下，看它认的是「一页」还是「一族互斥页」：

- 一帧就能判出是哪一页的（主页四个浮窗、五个出征标签、四种准备页），收成一个`checker.py`
  里的域探针入口，由 [registry](<./registry.md>) 的 `_DOMAIN_PROBERS` 统一调用；
- 只做页内导航、不判页面身份的（`sortie/battle/`），也收成单文件，入口是动作而不是判定。

### 2.4 依赖方向

~~~text
registry（确认表）
      ↓
checker/<页面>/__init__.py（稳定入口）
      ↓
checker.py（常量 + 识别 + 页面确认）
      ↓
application.ui.template（模板加载与缓存） → common.vision（识别算法）
~~~

禁止方向：

- checker 不点击设备、不算路、不改导航栈；
- 私有辅助不反向依赖 registry；
- 子包之间不互相导入（跨域复用要落到公共位置，例如模板加载）。

### 2.5 出口策略

包外只从各子包的 `__init__.py` 导入；`checker/__init__.py` 不导出实现。
各子包的私有辅助默认不是包外 API。

## 3. 能力总览

checker 的能力按页面分组，每组提供「确认」与（部分页面的）「读中心」两类入口：

| 能力 | 对外入口 | 所在子包 | 输入 | 输出 | 负责内容 |
| --- | --- | --- | --- | --- | --- |
| 登录流程确认 | `login.check_black_screen` / `check_update_prompt` / `check_loading` / `check_login_page` / `check_server_select` | `login/` | `ctx` + 三件套 | `bool` | 启动画面与登录页判断 |
| 区服定位 | `login.resolve_server_index` / `login.find_server_position` | `login/` | `ctx`、区服名 | `int` / `int \| None` | OCR 定位 + 静态映射兜底 |
| 主页与浮窗判层 | `home.read_home_layer` | `home/` | `ctx` | `tuple[PageName, ...]` | 一帧读七个模板，由深到浅返回这一帧能看到的全部层 |
| 主页浮窗事实 | `home.read_news_overlay` / `check_home_reward_overlay` / `check_home_reward_confirm` / `check_news_checked` | `home/` | `ctx` | 事实模型 / `bool` | 浮窗存在性、勾选状态 |
| 浮窗标记 | `home.mark_popups_settled` | `home/` | `ctx` | 无 | 回到干净主页后写三个浮窗处理标记 |
| 后院与二级页确认 | `backyard.check_backyard_page` 与四个二级页入口 | `backyard/` | `ctx` + 三件套 | `bool` | 后院主页与四个二级页身份 |
| 侧边栏体系确认 | `sidebar.check_sidebar_page` / `check_build_submenu` / `check_intensify_submenu` / `check_friend_page` | `sidebar/` | `ctx` + 三件套 | `bool` | 侧边栏、二级菜单、好友页 |
| 建造与强化标签 | `sidebar.build.check_dismantle_tab` / `sidebar.intensify.check_remold_tab` / `check_skill_tab` | `sidebar/` | `ctx` | `bool` | 页面内标签激活 |
| 出征域判层 | `sortie.read_sortie_layer` | `sortie/` | `ctx` | `tuple[PageName, ...]` | 一帧读浮窗标题 + 五个标签模板，由深到浅返回能同时看到的全部层 |
| 任务页与领奖 | `mission.check_mission_page` / `check_claim_all_button` / `check_mission_reward_confirm` | `mission/` | `ctx` + 三件套 | `bool` | 任务页身份与领奖浮窗 |
| 活动页面 | `event.stage_push.check_event_map_page` / `check_event_sortie_prepare` / `check_event_entry` | `event/` | `ctx`、活动标识 | `bool` | 活动入口、地图、章节浮窗 |
| 活动事实与解析 | `event.stage_push.read_event_map_state` / `read_event_type` / `read_event_stage` / `parse_stage` | `event/` | `ctx`、章节标识 | 事实模型 / 标识 / 执行参数 | 难度结论、任务绑定读取、章节解析 |
| 登录页按钮中心 | `login.read_enter_button_center` / `read_switch_entry_center` | `login/` | `ctx` | 归一化中心或 `None` | 给出按钮与换区入口中心 |
| 后院入口中心 | `backyard.read_canteen_entry_center` / `read_academy_entry_center` / `read_rank_room_entry_center` / `read_bath_entry_center` | `backyard/` | `ctx` | 归一化中心或 `None` | 给出四个入口中心供控制器点击 |
| 出征准备页判层 | `sortie.battle_preparation.read_battle_preparation_layer` | `sortie/battle_preparation/` | `ctx` | `tuple[PageName, ...]` | 一帧读四个准备页模板（共用同一 ROI），返回命中的准备页 |
| 演习浮窗按钮中心 | `sortie.exercise.read_overlay_close_center` / `read_overlay_refresh_center` / `read_overlay_challenge_center` | `sortie/exercise/` | `ctx` | 归一化中心或 `None` | 给出浮窗关闭 / 刷新 / 挑战按钮中心，供控制器点击 |
| 出征页内导航 | `sortie.battle.ensure_chapter` | `sortie/battle/` | `ctx`、`chapter`、`map_id` | 无（点击副作用） | 从当前章走到目标章、再翻到目标节点 |
| 活动按钮中心 | `event.stage_push.read_mode_button_center` / `read_sortie_prepare_center` | `event/` | `ctx`、活动标识 | 归一化中心或 `None` | 给出难度按钮与确认出征按钮中心 |
| 活动难度等待 | `event.stage_push.wait_event_mode` | `event/` | `ctx`、活动标识、目标难度 | `bool` | 重读难度直到切到目标值 |

## 4. 识别入口签名契约

### 4.1 三件套

除少数只读中心的入口外，页面确认入口统一收：

~~~python
def check_xxx_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = 1,
    interval_seconds: float = 0.5,
) -> bool:
~~~

| 参数 | 语义 |
| --- | --- |
| `ctx` | 提供设备服务与截图事实的 dispatch 上下文句柄 |
| `absent` | `False` 判出现（前识别），`True` 判消失（后识别） |
| `attempts` | 识别次数；默认只探当前一帧 |
| `interval_seconds` | 两次识别之间的等待秒数 |

### 4.2 节奏默认值写在签名里

**节奏默认值属于各 checker 自己**，注册表不兼职配节奏。页面切换动画长的页面（主页、后院、任务页）
默认给足重试，只做定位的入口默认只探一帧；调用方需要覆盖时直接传参。

### 4.3 四条硬要求

| 要求 | 原因 |
| --- | --- |
| 只读事实，不点击、不导航、不抛业务错误 | 动作归控制器，流程归 `service.py` |
| 节奏默认值写在签名里 | [registry](<./registry.md>) 不兼职配节奏 |
| ROI 的像素尺寸比模板各边大 1px | 换算用截断，等于模板时会小 1px 导致匹配失败 |
| 包入口只导出稳定入口 | 上层从包入口导入，不摸子包内部的 `checker.py` |

## 5. 模板加载

模板统一走 [application.ui.template](<../template.md>) 的 `load_ui_template`，它按
`(namespace, filename, name)` 缓存，同一组参数只读盘解码一次。

各子包在 `checker.py` 顶部声明自己的模板命名空间（相对应用模板根 `application/`，例如
`controller/home`）与模板文件名，`_load_template` 负责拼接调用。

**调用方式必须是模块限定名** `template.load_ui_template(...)`，不要写成
`from ... import load_ui_template`：测试通过 monkeypatch 模块属性替换模板加载，导入对象会破坏这个打桩点。

## 6. 活动 checker：event/stage_push

活动域比普通页面多两件事：

1. **活动玩法校验**：入口收到 `event_type` 时用模块私有 `_require_activity` 确认调用方选对了 checker，
   不一致抛 `ValueError`；
2. **任务绑定读取**：`read_event_type` / `read_event_stage` 从 `ctx` 读任务绑定的活动玩法与章节，
   缺失时抛 `NavigationError`。

活动模板按期号外挂（`event/stage_push_<期号>`），换期只改 `checker.py` 顶部的期号与模板目录。

## 7. 统一配置

本模块无运行时配置。模板路径、ROI、期望文本都是静态校准数据，放在各子包 `checker.py` 的常量区。

## 8. 错误约定

| 错误 | 定义位置 | 触发条件 | 处理者 | 是否可重试 |
| --- | --- | --- | --- | --- |
| `ValueError` | 各 checker | 入参非法（未知标签名、活动玩法与 checker 不匹配、章节标识非法） | 调用方 | 否，属于编程错误 |
| `NavigationError` | `types.py` | 任务缺少活动绑定（`read_event_type` / `read_event_stage`） | `service.py` 与 dispatch | 由上层决定 |

识别失败（画面里没有目标）不抛异常，返回 `False` 或 `None`，由调用方决定怎么处理。

## 9. 日志约定

通道为 `ui`（多数子包）与 `ui.login`（登录域），均经 `common.system.logger.get_logger`。

| 级别 | 记录内容 |
| --- | --- |
| `DEBUG` | 识别事实：模板是否命中、读到的中心、按钮模式等；全层扫描期间整体静默 |
| `INFO` | 区服定位成功（`login.checker`） |
| `WARNING` | 区服定位失败与兜底（`login.checker`） |

**同一事实只记一次**：同一子包内不重复打印已经记录的事实。

## 10. 公开出口和调用边界

### 10.1 稳定出口

各子包 `__init__.py` 的 `__all__` 即稳定出口清单，例如：

| 出口 | 来源 | 调用者可以做什么 | 调用者不能做什么 |
| --- | --- | --- | --- |
| `login.check_login_page` 等 | `login/__init__.py` | 注册为到达确认、按顺序判断启动画面 | 依赖内部识别细节 |
| `home.read_home_layer` | `home/__init__.py` | 注册为主页判层入口 | 自行拼装浮窗判断 |
| `sortie.read_sortie_layer` | `sortie/__init__.py` | 注册为域探针、按标签与浮窗判层 | 复用它的模板自己拼别的判定 |
| `sortie.exercise.read_overlay_*_center` | `sortie/exercise/__init__.py` | 由浮窗边动作读中心后传给控制器 | 用固定坐标代替模板中心 |
| `sortie.battle.ensure_chapter` | `sortie/battle/__init__.py` | 由导航边按参数调用 | 在别处重复实现选章选节 |
| `sortie.battle_preparation.read_battle_preparation_layer` | `sortie/battle_preparation/__init__.py` | 注册为域探针 | 逐个准备页写 checker 重复截图 |
| `event.stage_push.*` | `event/stage_push/__init__.py` | 注册确认、读活动事实与解析章节 | 绕过 `event_type` 校验 |

### 10.2 内部内容

各子包内的私有辅助（`_read_home_hits`、`_load_template`、`_require_activity`、
`_select_target_chapter`、`_parse_chapter_label` 等）都是内部内容。
测试直接调用它们不构成生产出口。

## 11. 模块维护方法

### 11.1 新增一个页面 checker

1. 在 `types.py` 的 `PageName` 加成员；
2. 在对应子包下建（或复用）`checker.py`，常量、识别和页面确认写在一起；
3. 写确认入口，签名用三件套，节奏默认值写在签名里；
4. 从子包 `__init__.py` 导出；
5. 在 [registry](<./registry.md>) 的 `_PAGE_CHECKERS` 注册；如果这一页和同族页面共用一块
   识别区域、一帧就能判出是哪一页，就写域探针入口，改注册到 `_DOMAIN_PROBERS` 与 `_DOMAIN_PAGES`；
6. 在 `testing/application/ui/navigation/checker/` 加对应的 focused 单测；
7. 跑 `pytest testing/application/ui/navigation/checker testing/application/ui/navigation`。

### 11.2 新增一个 checker 子包

只有当页面拥有独立依赖、独立校准数据或独立变化节奏时才建子包。子包必须至少有一个真实职责，
不为凑结构创建空文件。

### 11.2.1 域探针入口的写法

一次 `expect_template` 传齐本域全部模板，**返回这一帧能同时看到的全部层**（`tuple[PageName, ...]`，
按「上层在前」排序），而不是只返回第一层：浮窗出现时顶部标签栏往往没被遮住，两层会同时命中。
`read_home_layer`、`read_sortie_layer`、`read_battle_preparation_layer` 都是这个形状，共用的 ROI 只声明一份。

判断「到没到某个域页面」时取 `max(layers, key=depth_of)` 比目标页，不能用 `in`（会放过「上一层还开着」）。

### 11.3 新增一个活动玩法

1. 在 `event/` 下新建 `<玩法>/`，沿用单文件 `checker.py`；
2. `checker.py` 顶部声明 `ACTIVITY`、`PERIOD` 与 `TEMPLATE_NAMESPACE`（`event/<玩法>_<期号>`）；
3. `checker.py` 用私有 `_require_activity` 校验玩法标识；
4. 在 [registry](<./registry.md>) 的确认表与可达表里按玩法分发；
5. 补 focused 单测与实机 case。

### 11.4 换期（每期活动都做）

只改本期活动 `checker.py` 的 `PERIOD`、模板目录与期望文本；
识别结构不动。

### 11.5 删减能力

1. grep 确认没有调用方（含 [registry](<./registry.md>)、测试、工具与文档引用）；
2. 删除实现与包入口导出；
3. 删除 [registry](<./registry.md>) 里的注册项与相关边；
4. 删除或修正本文件、子包文档与父文档里的引用；
5. 跑门禁。

### 11.6 参数传入与穿透规则

| 参数 | 来源 | 规则 |
| --- | --- | --- |
| `ctx` | 调用方传入 | checker 只读，不持有 |
| `absent` / `attempts` / `interval_seconds` | 调用方按需覆盖，缺省用签名默认 | [executor](<./executor.md>) 的探测固定传 `attempts=1` |
| `event_type` | 调用方传入活动标识 | 入口内部校验，不一致抛 `ValueError` |
| 活动玩法与章节绑定 | `ctx.read_event_type` / `read_event_stage` | 由 checker 自己读，调用方不预先算好再传 |

## 12. 验收门禁

| 检查 | 手段 |
| --- | --- |
| 包入口 import smoke | `python -c "from autowsgr.application.ui.navigation.checker import login, home, sortie"` |
| 静态检查 | `ruff check autowsgr/application/ui/navigation/checker` |
| 模块单测 | `pytest testing/application/ui/navigation/checker` |
| 识别实机验证 | `python tools/debug_toolkit/main.py e2e --no-launch nav_chain`（含活动时补 `--event-type` / `--event-stage`） |
| ROI 与模板覆盖 | 变更 ROI 后至少跑一次相关识别验证 |
| 文档与代码一致 | 本文件的子项表与 `checker/` 目录一致；`git diff --check` |
