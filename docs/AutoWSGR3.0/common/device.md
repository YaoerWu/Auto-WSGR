# common/device —— 设备能力

源码目录：`autowsgr/common/device/`

## 1. 模块定位

**负责**：连接设备（ADB 控制 + Scrcpy 视频/控制通道）、输入（点击/滑动/长按/按键/文本）、截图、模拟器进程生命周期（启动/停止/重启/等待上线）、分辨率查询、操作间延迟。

**不负责**：

- 不判断页面、不识别画面、不等待"目标出现"（等待策略在 `common.vision` 与调用方）；
- 不做导航、不做业务流程、不知道页面语义；
- 不决定"点哪里"，坐标由控制器给，且一律是**相对坐标**（0–1）；
- 不管理任务生命周期（那是 `dispatch`）。

## 2. 目录与文件

```text
autowsgr/common/device/
├── __init__.py                只导出 service 子模块；DeviceService / DeviceInfo 由 service.py 导出
├── service.py                 唯一公开门面 DeviceService，把输入/截图/生命周期转给下层
├── config.py                  DeviceConfig：ADB 地址、Scrcpy 参数、模拟器类型与路径、操作延迟
├── errors.py                  DeviceError 分支与 GameError 分支
├── device_engine/
│   ├── session.py             DeviceSession：配置 + serial + adb_device + scrcpy + lifecycle 的持有者
│   ├── foundation/
│   │   ├── platform.py        OSType / EmulatorType 枚举与 detect_host_operating_system
│   │   └── delay.py           进程级操作延迟区间与 calculate_operation_delay
│   └── orchestration/
│       ├── connection.py      连接/断开/重连/是否已连接，产出 DeviceInfo
│       ├── operation.py       点击/滑动/长按/按键/文本/应用启停/display 查找的转发层
│       ├── screenshot.py      抓帧与保存截图（走 common.system.files.save_image）
│       ├── discovery.py       按 serial 正则识别模拟器类型（雷电/MuMu/蓝叠）
│       └── lifecycle/         模拟器进程管理：service.py 工厂 + base/windows/macos/linux 实现
├── adb_engine/executor.py     ADB 定位与命令：设备列表、shell、服务重启、截图解码
└── scrcpy_engine/executor.py  Scrcpy 引擎：视频流与控制通道、输入事件、分辨率、首帧等待
```

## 3. 依赖关系

```text
        application.runtime（装配）· controller.page · common.vision
                          │ ctx.runtime.ctrl.<方法>
                          ▼
                 ┌──────────────────┐
                 │  DeviceService   │  ← 唯一公开门面
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │  DeviceSession   │  配置 / serial / 引擎句柄
                 └───┬──────────┬───┘
                     ▼          ▼
        orchestration/*     adb_engine + scrcpy_engine
                     │
                     ▼
        foundation（平台与延迟）· common.system.files
```

- **上层谁调它**：`application/runtime` 负责创建并持有 `DeviceService`，对外暴露成 `ctx.runtime.ctrl`；`controller/page.py` 只调 `click` / `swipe`；`common/vision.screenshot` 调 `screenshot()`；`dispatch/startup.py` 调 `check_app_running` / `start_app` / `stop_app` / `follow_display`。
- **它下层依赖谁**：`adbutils`（ADB）、`scrcpy` 服务端 jar（随包 `scrcpy-server.jar`，协议版本 5.0.1）、`common.system.files`（保存截图）、`common.system.errors`。

## 4. 调用入口与出口

### 4.1 连接

```python
class DeviceService:
    def __init__(self, config: DeviceConfig | None = None) -> None
    def connect(self, package: str | None = None) -> DeviceInfo
    def is_connected(self) -> bool
    def disconnect(self) -> None
    def reconnect(self) -> DeviceInfo
    @property
    def resolution(self) -> tuple[int, int]
```

`DeviceInfo` 是冻结数据类：`serial: str` + `resolution: tuple[int, int]`。连接内部最多重试 `_ADB_CONNECTION_MAX_ATTEMPTS=3` 次、间隔 `_ADB_CONNECTION_RETRY_DELAY_SECONDS=2.0` 秒。

### 4.2 输入

```python
def click(self, x: float, y: float, *, delay: bool = False) -> None
def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5, *, delay: bool = False) -> None
def long_tap(self, x: float, y: float, duration: float = 1.0) -> None
def key_event(self, key_code: int, *, delay: bool = False) -> None
def text(self, content: str, *, delay: bool = False) -> None
```

坐标全部归一化到 0–1；`delay=True` 表示这一步之后按 `DeviceConfig.DEVICE_OPERATION_DELAY_MIN/MAX` 的区间随机等待（区间由 `foundation/delay.py` 的 `configure_operation_delay_bounds` 设置）。

### 4.3 应用与截图

```python
def start_app(self, package: str) -> None
def follow_display(self, package: str) -> None   # 轮询 15s / 0.5s，等待应用显示到独立屏
def stop_app(self, package: str) -> None
def check_app_running(self, package: str) -> bool
def shell(self, command: str) -> str
def screenshot(self) -> numpy.ndarray             # RGB
def save_screenshot(self, path: str | Path, *, allowed_root: str | Path) -> None
```

`follow_display` 是多显示器模拟器的必需步骤：不调用的话截图拿到的是桌面帧而不是游戏帧。

### 4.4 模拟器生命周期

```python
def check_emulator_running(self) -> bool
def start_emulator(self) -> None
def stop_emulator(self) -> None
def restart_emulator(self) -> None
def wait_emulator_online(self, timeout: float = 120) -> None
```

实现按宿主系统分派：`orchestration/lifecycle/service.py` 的 `create_emulator_process_manager(config, os_type=None, serial=None)` 根据 `detect_host_operating_system()` 选 windows/macos/linux 实现。模拟器类型由 `discovery._EMULATOR_SERIAL_RULES` 的正则表判定（例如 `^emulator-\d+$ → 雷电`、`^127\.0\.0\.1:1638[4-9]$ → MuMu`、`127.0.0.1:5555-5559 → 蓝叠`）。

### 4.5 错误

`DeviceError(CommonError)` 之下分 `DeviceConnectionError` / `DeviceNotFoundError`；`GameError(DeviceError)` 之下分 `NetworkError` / `ResourceError`。连接类失败抛前者，游戏内网络/资源异常抛后者。

## 5. 怎么维护

- **新增输入方式**：在 `scrcpy_engine/executor.py` 加底层事件，在 `orchestration/operation.py` 加转发函数，最后才在 `service.py` 暴露成公开方法。三层缺一不可，别在 service 里直接拼 adb 命令。
- **新增模拟器类型**：① 在 `foundation/platform.py` 的 `EmulatorType` 加成员；② 在 `discovery._EMULATOR_SERIAL_RULES` 加 serial 正则；③ 在 `orchestration/lifecycle/` 下加对应进程管理实现并在 `service.py` 的工厂里登记。
- **坐标永远是相对值**：不要在这里接受像素坐标；像素换算只在 `common.vision` 的 ROI/Template 里发生。
- **不要绕过 `DeviceSession`**：引擎句柄、serial、lifecycle 都挂在 session 上，直接 new 引擎会让重连与生命周期状态分叉。
- **延迟不要写死 sleep**：统一走 `delay.py` 的进程级区间，否则配置里的延迟开关会失效。
- **`service.py` 是唯一公开出口**：`device_engine/`、`adb_engine/`、`scrcpy_engine/` 里的函数都是内部实现，上层不得 import。
- 已知排版瑕疵：`service.py` 里若干节注释被缩进进了上一个方法体（例如"连接模拟器"注释落在 `return` 之后），改动该文件时可顺手归位。

## 6. 索引

- [返回总览](../README.md)
- [common/system.md](system.md) —— 截图落盘用的 `save_image` 与错误基类
- [common/vision.md](vision.md) —— 消费截图的识别层
- [application/navigation.md](../application/navigation/README.md) —— 导航器通过控制器间接使用设备
- [application/controller.md](../application/controller/README.md) —— 点击坐标的产出方
