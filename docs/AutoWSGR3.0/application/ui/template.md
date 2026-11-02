# application-ui-template 架构说明

版本：AutoWSGR-3.0 第 1 版
状态：生效
适用范围：`autowsgr/application/ui/template.py`
实现基线：`codex/20260913-shiinaskuya-upgrade-7b3e`，2026-10-13

## 1. 模块定位

template 是 **application 层**的公共模板加载模块。它把「应用层某个命名空间下的模板文件名」
变成「已加载并缓存的模板对象」，供导航器与页面控制器共用。

它明确不负责：识别规则与阈值（属于各调用方）、页面语义、图像算法（属于 `common.vision`）、
模板根之外的路径解析。

所有权：

- 模板根 `UI_TEMPLATE_ROOT` 由本模块独占持有；
- 已加载的模板由本模块的缓存持有，进程内复用；
- 模板文件与路径安全由 `common.vision` 负责；
- 本模块无运行时状态、无日志。

## 2. 模块架构

### 2.1 文件形态

~~~text
autowsgr/application/ui/
└── template.py      # UI 层模板加载与缓存
~~~

### 2.2 文件内部结构

| 分区 | 内容 |
| --- | --- |
| 常量 | `UI_TEMPLATE_ROOT`：应用层模板根，命名空间从它起算 |
| 能力 | `load_ui_template`：拼接路径、加载、按参数缓存 |

### 2.3 依赖方向

~~~text
navigation.checker / controller（调用方）
        ↓
application.ui.template
        ↓
common.vision.adapters.template_matching（load_template）
        ↓
common.vision.opencv.executor（读盘解码）
~~~

禁止方向：

- 本模块不依赖 navigation 或 controller（只能被它们调用）；
- 本模块不做识别，也不解释模板的业务含义；
- 本模块不缓存截图或识别结果，只缓存模板本身。

### 2.4 出口策略

`load_ui_template` 与 `UI_TEMPLATE_ROOT` 是稳定出口；缓存是实现细节，不对外暴露失效入口。

## 3. 能力总览

| 能力 | 对外入口 | 输入 | 输出 | 负责内容 | 不负责内容 |
| --- | --- | --- | --- | --- | --- |
| 加载 UI 模板 | `template.load_ui_template` | 命名空间、文件名、业务名称 | `Template` | 拼路径、加载、缓存 | 识别规则、阈值、ROI |

## 4. 加载 UI 模板

### 4.1 能力说明

按 `application/<命名空间>/<文件名>` 定位模板，交给 `common.vision` 加载，并按加载参数缓存。
模板文件在进程运行期间不变，因此同一组参数只读盘解码一次；识别重试不会反复读盘。

### 4.2 稳定入口

~~~text
template.load_ui_template(namespace: str, filename: str, *, name: str) -> Template
~~~

| 参数 | 必填 | 语义 |
| --- | --- | --- |
| `namespace` | 是 | 相对应用模板根的目录，例如 `controller/home` |
| `filename` | 是 | 命名空间内的模板文件名 |
| `name` | 是（仅关键字） | 模板业务名称，用于识别日志与匹配结果 |

返回已加载的 `Template`；相同参数重复调用返回同一个对象。无副作用，不改上下文与设备。

### 4.3 调用示例

~~~python
from autowsgr.application.ui import template

home_main = template.load_ui_template(
    'controller/home',
    'HOME_MAIN_720P.png',
    name='home_main',
)
~~~

### 4.4 错误和副作用

| 场景 | 行为 | 异常/结果 | 处理者 |
| --- | --- | --- | --- |
| 路径越界（绝对路径或含 `..`） | 拒绝 | `ValueError` | 调用方（属于编程错误） |
| 模板文件不存在 | 失败 | `FileNotFoundError` | 调用方与资源维护者 |

缓存对异常不做记忆：加载失败会重新抛，下次调用重新尝试。

### 4.5 维护规则

**调用方必须使用模块限定名** `template.load_ui_template(...)`，不要写成
`from ... import load_ui_template`：测试通过 monkeypatch 模块属性替换模板加载，导入对象会破坏这个打桩点。

## 5. 统一配置

本模块只有一个常量，不是可覆写配置：

| 常量 | 值 | 作用 |
| --- | --- | --- |
| `UI_TEMPLATE_ROOT` | `'application'` | 应用层模板根目录，位于 `common.vision` 的模板根下；命名空间从它起算 |

模板根与来源分辨率属于 `common.vision`，本模块不重复定义。

## 6. 错误约定

本模块不定义错误类型，只透传下层异常：`ValueError`（路径非法）与 `FileNotFoundError`（文件缺失）。

## 7. 日志约定

本模块不记录日志。模板匹配的命中与「差一点就中」由 `common.vision` 记录，
识别事实由各 checker 的 `recognition.py` 记录。

## 8. 公开出口和调用边界

### 8.1 稳定出口

| 出口 | 来源 | 调用者可以做什么 | 调用者不能做什么 |
| --- | --- | --- | --- |
| `template.load_ui_template` | `template.py` | 按命名空间加载模板 | 依赖缓存的内部结构 |
| `template.UI_TEMPLATE_ROOT` | `template.py` | 拼接自己的命名空间 | 修改它 |

### 8.2 内部内容

`@cache` 装饰的缓存与函数内部拼接都是实现细节，不提供失效或清理入口。

## 9. 模块维护方法

### 9.1 新增一个模板命名空间

在调用方自己的 `constants.py` 声明命名空间片段（相对 UI 模板根）与文件名，
调用 `load_ui_template` 即可，本模块不需要改动。

### 9.2 运行期替换模板文件

缓存是进程级的：替换模板文件后需要重启进程才会生效。需要热更新时应先评估是否引入失效入口，
不要直接删缓存绕过。

### 9.3 新增公共能力

只有当 UI 层出现第二项公共能力（坐标换算、通用 ROI 处理、页面校准数据读取等）时，
才把本模块整合成 `application/ui/calibration` 或 `application/ui/platform` 包；
只有一项能力时不建包。

### 9.4 删减能力

先 grep 确认没有调用方（含导航器、控制器、测试与文档），再删除实现与本文档。

## 10. 验收门禁

| 检查 | 手段 |
| --- | --- |
| 公共入口 import smoke | `python -c "from autowsgr.application.ui import template"` |
| 静态检查 | `ruff check autowsgr/application/ui/template.py` |
| 缓存行为 | 同一参数两次调用返回同一对象 |
| 调用方回归 | `pytest testing/application/ui/navigation/checker testing/application/ui/navigation` |
| 实机链路 | `python tools/debug_toolkit/main.py e2e --no-launch --event-type stage_push --event-stage EX1 nav_chain` |
| 文档与代码一致 | 本节与 `template.py` 的出口一致；`git diff --check` |
