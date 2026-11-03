"""验证模块配置基类与换船舰名映射的解析规则。

直接调用方：项目测试运行器。

直接依赖：pytest、pydantic、autowsgr.config 及其模块配置模型。

边界：只构造配置对象，不读取文件、不连接设备、不访问 OCR 引擎。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from autowsgr.application.fleet_select import service as service_module
from autowsgr.application.fleet_select.config import FleetSelectConfig
from autowsgr.application.fleet_select.rules.shipnames import get_active_ship_name_aliases
from autowsgr.application.fleet_select.types import FleetSelectMode
from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.system.config import LogConfig
from autowsgr.config import UserConfig


@pytest.mark.parametrize(
    'config_type',
    [LogConfig, DeviceConfig, FleetSelectConfig, UserConfig],
)
def test_unknown_fields_are_rejected(config_type: type) -> None:
    """配置树上的每个模型都拒绝未声明字段。"""
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        config_type.model_validate({'NOT_A_FIELD': 1})


def test_user_config_aggregates_module_configs() -> None:
    """顶层配置默认携带日志、设备和换船三块模块配置。"""
    config = UserConfig()

    assert isinstance(config.LOG, LogConfig)
    assert isinstance(config.DEVICE, DeviceConfig)
    assert isinstance(config.FLEET_SELECT, FleetSelectConfig)
    assert config.FLEET_SELECT.SHIP_NAME_MAP == {}


def test_config_tree_is_immutable() -> None:
    """配置对象在构造后不可修改。"""
    config = FleetSelectConfig()

    with pytest.raises(ValidationError):
        config.SHIP_NAME_MAP = {'AIII': '希尔德布兰德'}


def test_ship_name_map_accepts_mapping() -> None:
    """映射写法按系统标准船名指向游戏内显示船名。"""
    config = FleetSelectConfig.model_validate(
        {'SHIP_NAME_MAP': {'AIII': '希尔德布兰德', 'U-47': 'U-47·狼群'}},
    )

    assert config.SHIP_NAME_MAP == {'AIII': '希尔德布兰德', 'U-47': 'U-47·狼群'}
    assert config.SHIP_NAME_MAP.get('U-47') == 'U-47·狼群'
    assert config.SHIP_NAME_MAP.get('新奥尔良', '新奥尔良') == '新奥尔良'


def test_ship_name_map_accepts_multiline_text() -> None:
    """多行文本同时接受中英文冒号和行内空格，多余的行被跳过。"""
    config = FleetSelectConfig.model_validate(
        {
            'SHIP_NAME_MAP': (
                'AIII: 希尔德布兰德\n85工程 ： 契卡洛夫\n# 注释行会被跳过\n缺少冒号的行也被跳过\n'
            ),
        },
    )

    assert config.SHIP_NAME_MAP == {'AIII': '希尔德布兰德', '85工程': '契卡洛夫'}


def test_ship_name_map_rejects_one_ship_with_multiple_display_names() -> None:
    """一艘标准舰名写了多个游戏内舰名时直接报错，不做静默取舍。"""
    with pytest.raises(ValidationError, match='一行只写一艘船'):
        FleetSelectConfig.model_validate({'SHIP_NAME_MAP': 'U-47: U-47·狼群， 狼群'})


def test_ship_name_map_rejects_duplicate_display_name() -> None:
    """两艘标准舰名抢同一个游戏内舰名时报错，避免搜索时分不清目标。"""
    with pytest.raises(ValidationError, match='同时映射自'):
        FleetSelectConfig.model_validate(
            {'SHIP_NAME_MAP': {'AIII': '希尔德布兰德', '85工程': '希尔德布兰德'}},
        )


def test_adjust_fleet_scopes_ship_name_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """映射只在换船编排期间生效，编排返回后立刻恢复。"""
    seen: dict[str, str] = {}

    def _fake_adjust_normal_fleet(*_args: object, **_kwargs: object) -> None:
        seen.update(get_active_ship_name_aliases())

    monkeypatch.setattr(
        service_module,
        'normal',
        SimpleNamespace(adjust_normal_fleet=_fake_adjust_normal_fleet),
    )
    service_module.adjust_fleet(
        object(),
        mode=FleetSelectMode.NORMAL,
        fleet_rules=[],
        ship_name_map={'AIII': '希尔德布兰德'},
    )

    assert seen == {'希尔德布兰德': 'AIII'}
    assert get_active_ship_name_aliases() == {}
