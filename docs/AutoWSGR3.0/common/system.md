# common/system —— 系统基础能力

源码目录：`autowsgr/common/system/`

## 1. 模块定位

**负责**：日志对象的创建与全局输出初始化、错误类型的根谱系、受限目录内的 YAML/图像读写、枚举基类、日志配置模型与模块配置基类。

**不负责**：

- 不解释文件里的业务字段（只保证路径、编码、解析、原子写入）；
- 不决定业务结果、页面状态、重试策略或业务日志文本；
- 不加载用户配置，只提供 `LogConfig` 与模块配置基类 `ModuleConfig`；
- 不定义页面或业务错误，只提供错误基类给上层继承。

它是整个仓库的叶子层：不 import 任何 `autowsgr.*` 模块（同包的 `config` 除外）。

## 2. 目录与文件

```text
autowsgr/common/system/
├── __init__.py  只导出 enums / errors / files / logger 四个子模块名
├── logger.py    get_logger（通道日志对象）与 setup_logger（sink 初始化、DEBUG 通道门控）
├── errors.py    五个错误基类：SystemError 与它的四类分支
├── files.py     load_yaml / save_yaml / load_image / save_image，全部带 allowed_root 边界
├── enums.py     BaseEnum / StrEnum / IntEnum，统一中文非法值报错
└── config.py    LOG_TIMEZONE（UTC+8）、ModuleConfig（模块配置基类）与 LogConfig
```

## 3. 依赖关系

```text
        application / business / dispatch / server
                 │  get_logger · errors · files · enums
                 ▼
        ┌────────────────────┐
        │  common.system     │────► loguru · PyYAML · pydantic · 标准库
        └────────────────────┘
                 ▲  ModuleConfig / LogConfig / LOG_TIMEZONE
        common.device · common.vision
```

- **上层谁调它**：所有模块用 `get_logger(channel)` 取日志对象；`common.device` 用 `files.save_image` 存截图；`common.vision` 用 `files.load_image` 读模板；各层错误类型继承 `errors` 的基类；各包枚举继承 `enums` 的基类。
- **它下层依赖谁**：loguru、PyYAML、pydantic 与标准库；图像能力在 `files` 内按需 import OpenCV/NumPy，不作为静态依赖。

## 4. 调用入口与出口

### 4.0 配置模型基类

```python
class ModuleConfig(BaseModel)   # model_config = {'frozen': True, 'extra': 'forbid'}
```

各模块的配置模型继承 `ModuleConfig`，一次性获得两条约束：构造后不可修改，
以及拒绝未声明字段（避免用户写错键名却静默生效）。字段名使用 UPPER_SNAKE_CASE，
与模块常量同一套命名规范；顶层 `UserConfig` 自己也继承它，因此整棵配置树都
不可变、都不接受未知键。

`ModuleConfig` 只管模型约束，不负责加载文件——读取 YAML 的入口在
`autowsgr.config.ConfigManager`。

### 4.1 日志

```python
def get_logger(channel: str) -> Logger
def setup_logger(config: LogConfig | None = None) -> None
```

- `get_logger` 返回绑定 `ch=channel` 的 loguru Logger，直接调 `debug/info/warning/error`。通道名约定用包路径的小写形式，例如 `'dispatch.startup'`、`'combat'`。
- `setup_logger` 是全局唯一初始化入口：先 `logger.remove()` 清旧 sink，再 `logger.configure(patcher=_src_patcher)`，然后挂 stderr 与文件两个 sink。文件路径为 `LOG_USER_DIR/autowsgr_{time:YYYY-MM-DD}.log`，切分与保留取 `LOG_ROTATION` / `LOG_RETENTION`；同时把 `adbutils` 的 Python logging 降到 WARNING。
- sink 格式是**技术 bootstrap 例外**：`{time} | {level} | {src} | {message}`。业务日志正文仍须按规范写 `[模块名] 位置 → 动作：附加信息`，sink 不替调用方组织业务语义。
- `_src_patcher` 把时间转成 `LOG_TIMEZONE`（UTC+8），把文件路径裁成 `相对路径:行号`（正斜杠）；未绑定通道的调用写成空字符串，保证格式化不炸。
- **DEBUG 门控**：`LogConfig` 中任意 `LOG_<NAME>_OPEN=True` 的字段会被 `_open_debug_channels` 推导成通道前缀 `<name>`（例如 `LOG_COMBAT_OPEN` → `combat`）。只有 `ch` 等于该前缀或以 `前缀.` 开头的 DEBUG 记录才输出；非 DEBUG 记录按 `LOG_LEVEL` 放行，且只接受 DEBUG/INFO/WARNING/ERROR 四级。

### 4.2 错误

```text
SystemError(Exception)
├── CommonError        公共能力错误（设备/视觉/配置）
├── ApplicationError   应用层错误（navigation、controller 抛它）
├── BusinessError      业务错误
└── DispatchError      调度与上下文错误
```

导航器的 `NavigationError(ApplicationError)`、设备的 `DeviceError(CommonError)` 都挂在这棵树上。上层捕获时按分支抓，不要抓 `Exception` 兜底。

### 4.3 文件边界

```python
def load_yaml(path: str | Path, *, allowed_root: str | Path) -> dict[str, Any]
def load_image(path: str | Path, *, allowed_root: str | Path) -> numpy.ndarray   # RGB
def save_yaml(yaml_mapping: dict[str, Any], path: str | Path, *, allowed_root: str | Path) -> None
def save_image(image: numpy.ndarray, path: str | Path, *, allowed_root: str | Path) -> None
```

- 四个函数都强制要求 `allowed_root`：路径先 `resolve()` 再 `relative_to(root)`，越界抛 `ValueError(f'路径超出允许目录: {target}')`。
- 读：`load_yaml` 空文件返回空映射，不存在抛 `FileNotFoundError(f'YAML 文件不存在: …')`；`load_image` 返回 RGB 数组，不存在抛 `FileNotFoundError(f'图像文件不存在: …')`，解码失败抛 `ValueError(f'无法解码图像文件: …')`。
- 写：`save_yaml` 先在目标目录写临时文件、`fsync` 后 `os.replace` 原子替换，`finally` 清理临时文件；`save_image` 走 `imencode` + `os.replace`，失败抛 `ValueError(f'无法编码图像文件: …')`。父目录不存在会自动创建。

### 4.4 枚举基类

```python
class BaseEnum(Enum)          # _missing_ 抛 ValueError('"<值>" 不是合法的 <类名> 取值。 支持: [<成员值…>]')
class StrEnum(str, BaseEnum)
class IntEnum(int, BaseEnum)
```text

上层枚举继承它们即可获得统一的中文非法值报错；成员值允许中文，用于日志与配置序列化。

## 5. 怎么维护

- **加一个日志通道**：在 `LogConfig` 里加 `LOG_<NAME>_OPEN: bool = False`，`_open_debug_channels` 按字段名自动推导，不用改 `logger.py`。
- **不要新增日志级别**：`_LEVEL_MAP` 固定四档，其他 loguru 级别会被 filter 丢弃。
- **不要绕过 `_resolve_path`**：新增任何文件能力都必须带 `allowed_root`，否则等于把仓外路径暴露给业务层。
- **写文件必须原子**：沿用"同目录临时文件 + `os.replace`"，不要改成直接 `open(target, 'w')`，中断会留下半个文件。
- **错误类型只能挂到已有分支下**：新增公共能力错误继承 `CommonError`，应用层错误继承 `ApplicationError`；`common` 内不许抛业务错误。
- **枚举不要重写 `_missing_`**：报错文案是统一契约，覆盖会让排查口径分裂。

## 6. 索引

- [返回总览](../README.md)
- [common/device.md](device.md) —— 设备连接、输入与截图
- [common/vision.md](vision.md) —— 识别能力出口
- [application/navigation.md](../application/navigation/README.md) —— `NavigationError` 的抛出方
- [application/controller.md](../application/controller/README.md) —— 页面识别与点击
