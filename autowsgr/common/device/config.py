"""模块功能：定义设备连接、Scrcpy 和操作时序的配置模型。

上层调用：
- common.device.service、common.device.adb_engine.executor 和 scrcpy_engine.executor：读取连接与输入配置。
- common.device.device_engine 的连接和生命周期流程：读取模拟器与操作时序配置。

下层依赖：
- Pydantic：提供字段校验和不可变模型。
- common.device.device_engine.foundation.platform：提供模拟器类型枚举。

边界：只校验配置值，不执行设备连接、进程控制或 Android 操作。
"""

from __future__ import annotations

from pydantic import Field

from autowsgr.common.device.device_engine.foundation.platform import EmulatorType
from autowsgr.common.system.config import ModuleConfig


class DeviceConfig(ModuleConfig):
    """保存 device 能力所需的 ADB、Scrcpy 和模拟器配置。"""

    # ── ADB 配置 ────────────────────────────────────────────────────────────

    ADB_CONNECTION: str | None = None  # 用户指定的 ADB 连接地址；为空时自动发现设备。

    # ── Scrcpy 配置 ─────────────────────────────────────────────────────────

    SCRCPY_MAX_SIZE: int = Field(default=0, ge=0)  # Scrcpy 视频最大边长；0 表示不限制。
    SCRCPY_BITRATE: int = Field(default=8_000_000, gt=0)  # Scrcpy 视频码率，单位为 bit/s。
    SCRCPY_MAX_FPS: int = Field(default=0, ge=0)  # Scrcpy 视频最大帧率；0 表示不限制。
    # Scrcpy 首帧和视频恢复等待上限，单位为秒。
    SCRCPY_SCREENSHOT_TIMEOUT: float = Field(
        default=10.0,
        gt=0.0,
        allow_inf_nan=False,
    )

    # ── 模拟器配置 ──────────────────────────────────────────────────────────

    DEVICE_EMULATOR_TYPE: EmulatorType = (
        EmulatorType.leidian
    )  # 模拟器类型，用于 serial 和路径推断。
    DEVICE_EMULATOR_PATH: str | None = None  # 模拟器宿主程序路径；为空时由平台能力解析。
    # 设备操作前随机延迟下界，单位为秒。
    DEVICE_OPERATION_DELAY_MIN: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    # 设备操作前随机延迟上界，单位为秒。
    DEVICE_OPERATION_DELAY_MAX: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)


__all__ = ['DeviceConfig']
