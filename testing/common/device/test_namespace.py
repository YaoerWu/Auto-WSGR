"""验证 common.device 包只导出 service 命名空间。

直接调用方：测试与业务层按 `from autowsgr.common.device import service` 使用。
直接依赖：autowsgr.common.device.__init__ 的导出声明。
边界：只校验导出面，不触碰真实 ADB 或模拟器。
"""

from autowsgr.common import device
from autowsgr.common.device import service


def test_device_package_exports_only_service_namespace() -> None:
    """包级导出只暴露 service 命名空间，不直接暴露实现类。"""
    assert device.__all__ == ['service']
    assert device.service is service
    assert not hasattr(device, 'DeviceService')


def test_service_module_declares_public_classes() -> None:
    """service 模块声明 DeviceInfo 与 DeviceService 两个公开入口。"""
    assert set(service.__all__) == {'DeviceInfo', 'DeviceService'}
