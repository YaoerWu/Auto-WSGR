"""验证宿主系统识别、默认 serial 映射与模拟器类型判断。

直接调用方：生命周期工厂与设备发现逻辑。
直接依赖：sys.platform、环境变量与 /proc 文件。
边界：只测纯映射与探测分支，不启动模拟器。
"""

import io

import pytest

from autowsgr.common.device.device_engine.foundation import platform as platform_module
from autowsgr.common.device.device_engine.foundation.platform import EmulatorType, OSType


def test_default_serial_matrix_covers_supported_and_unsupported_pairs() -> None:
    """按模拟器类型与宿主系统给出约定 serial，没有约定的组合明确报错。"""
    for emulator_type, os_type, serial in (
        (EmulatorType.leidian, OSType.windows, 'emulator-5554'),
        (EmulatorType.bluestacks, OSType.windows, '127.0.0.1:5555'),
        (EmulatorType.mumu, OSType.windows, '127.0.0.1:16384'),
        (EmulatorType.bluestacks, OSType.macos, '127.0.0.1:5555'),
        (EmulatorType.mumu, OSType.macos, '127.0.0.1:5555'),
    ):
        assert platform_module.calculate_default_emulator_serial(emulator_type, os_type) == serial

    for emulator_type, os_type in (
        (EmulatorType.yunshouji, OSType.windows),
        (EmulatorType.leidian, OSType.macos),
        (EmulatorType.mumu, OSType.linux),
    ):
        with pytest.raises(ValueError, match='设置默认 serial'):
            platform_module.calculate_default_emulator_serial(emulator_type, os_type)


def test_detect_host_operating_system_accepts_windows_macos_and_wsl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """win32/darwin 直接判定；Linux 只有 WSL 接受；非 WSL 与未知平台都报错。"""
    for platform_name, expected in (
        ('win32', OSType.windows),
        ('darwin', OSType.macos),
    ):
        monkeypatch.setattr(platform_module.sys, 'platform', platform_name)
        assert platform_module.detect_host_operating_system() is expected

    monkeypatch.setattr(platform_module.sys, 'platform', 'linux')
    monkeypatch.setenv('WSL_DISTRO_NAME', 'Ubuntu')
    assert platform_module.detect_host_operating_system() is OSType.linux

    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.delenv('WSL_INTEROP', raising=False)

    def _fail_open(*_args: object, **_kwargs: object) -> object:
        raise OSError

    monkeypatch.setattr('builtins.open', _fail_open)
    with pytest.raises(ValueError, match='暂不支持非 WSL 的 Linux 系统'):
        platform_module.detect_host_operating_system()

    monkeypatch.setattr(platform_module.sys, 'platform', 'freebsd')
    with pytest.raises(ValueError, match='不支持的操作系统: freebsd'):
        platform_module.detect_host_operating_system()


def test_wsl_environment_uses_variables_then_proc_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任一 WSL 环境变量存在即视为 WSL；都缺失时回退读 /proc，仍无证据则判否。"""
    for environment_variable, value in (
        ('WSL_DISTRO_NAME', 'Ubuntu'),
        ('WSL_INTEROP', '/run/WSL/1_interop'),
    ):
        monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
        monkeypatch.delenv('WSL_INTEROP', raising=False)
        monkeypatch.setenv(environment_variable, value)
        assert platform_module.check_wsl_environment() is True

    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.delenv('WSL_INTEROP', raising=False)

    def _fake_open(path: str, *_args: object, **_kwargs: object) -> io.StringIO:
        if path == '/proc/sys/kernel/osrelease':
            raise OSError
        return io.StringIO('Linux version 5.15.0-microsoft-standard-WSL2')

    monkeypatch.setattr('builtins.open', _fake_open)
    assert platform_module.check_wsl_environment() is True

    def _fail_open(*_args: object, **_kwargs: object) -> object:
        raise OSError

    monkeypatch.setattr('builtins.open', _fail_open)
    assert platform_module.check_wsl_environment() is False
