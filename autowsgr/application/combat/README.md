# Combat Application Foundation

`application/combat` 是战斗引擎：从点下【开始出征】到退出战果页的完整一场。
它不负责进图选章、编队换船、补给修理，也不决定打几场、打完去哪——这些属于
`business/combat` 编排层。

战斗内的全部识别与点击不放这里，放
`autowsgr/application/controller/sortie/battle_engine/`。引擎只做编排：判当前阶段、
选下一阶段、按转移图推进。

## 对外入口

跨模块只从 `autowsgr.application.combat` 导入，唯一执行入口是 `run_battle`：

```python
from autowsgr.application.combat import run_battle

result = run_battle(ctx, plan, ship_stats=ship_stats, stop_requested=stop.is_set)
```

`ctx` 是 `ContextHandle`，战斗引擎通过它截图、点击、读配置；不再接受设备对象。

## 目录

```text
application/combat/
├── types.py            对外类型：战况、阵型、索敌动作、战斗标记、战斗模式，
│                       以及引擎对编排层的契约 BattlePlan / BattleNodeDecision
├── errors.py           战斗异常
├── history.py          战斗事件、单场结果、整场结果
├── service.py          run_battle，唯一对外入口
├── engine/             战斗监控（真正的引擎）
│   ├── types.py            CombatPhase / PhaseBranch
│   ├── transitions.py      阶段转移图与模式派生表
│   ├── recognizer.py       等下一个阶段出现
│   ├── preparation.py      准备阶段编排（出征后的加速轮询、船坞满记账）
│   ├── loop.py             主循环
│   ├── handlers.py         按阶段分派的通用处理
│   ├── decision.py         索敌 / 阵型 / 前进决策
│   └── settlement.py       战果与掉落结算
├── node_tracking/      地图节点追踪
│   ├── types.py            NodePosition
│   ├── constants.py        地图数据根目录与追踪参数
│   ├── map_data.py         地图 YAML 加载
│   ├── algorithm.py        判节点（纯函数：选点、距离、射线）
│   └── tracker.py          追踪状态
└── rules/              规则层
    ├── enemy.py            条件与规则引擎
    └── node.py             破损判定
```

## 依赖方向

```text
business/combat（编排：打几场、去哪、何时换船修理）
        ↓ plan / ship_stats
application/combat（引擎：一场战斗）
        ↓
application/controller/sortie/battle_engine（战斗 checkers 与 page）
        ↓
common/vision（模板、像素、OCR）→ common/device
```

引擎内部也单向：`service` → `engine` → `node_tracking` / `rules`。下层不反向依赖上层，
`engine` 之外的子包也不互相调用。

`controller/.../battle_engine` 由两个 checker 子包组成：`monitor/` 判 16 个战斗阶段
与结算信息，`tracking/` 读地图上的船位置与索敌页；`page.py` 是战斗内的全部点击。
阶段枚举 `CombatPhase` 定义在 `battle_engine/monitor/types.py`，引擎从那里取，
不重复定义。

计划由编排层构造后传进来，引擎不 import `business.combat.plan`：`service.run_battle`
的 `plan` 只需要满足 `types.BattlePlan` 协议（模式、章节、转移图、节点决策等），
`get_node_decision` 的返回值只需要满足 `types.BattleNodeDecision`（是否迂回、是否夜战）。

## 尚未还原的识别能力

以下两项仍为降级占位（打 warning，不参与决策），待第二阶段随 checker 补做：

- 敌方编成（旧实现依赖已删除的原生识别库）；
- 掉落舰名与舰种（旧实现依赖旋转文字 OCR）。

## 资源

战斗模板位于 `resources/image/combat/`，地图节点数据位于
`resources/data/map/{normal,event}/`。
