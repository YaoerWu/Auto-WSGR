"""验证 application/controller/types 的舰种枚举契约。

直接调用方：各页面包与 fleet_select。

直接依赖：autowsgr.application.controller.types。

边界：只检查成员值与字符串语义，不读取图像或页面坐标。
"""

from __future__ import annotations

from autowsgr.application.controller.types import ShipType


def test_ship_type_covers_game_categories_with_display_names() -> None:
    """舰种成员值即游戏内显示名称，未知取值按中文枚举语义报错。"""
    assert ShipType.CV == '航母'
    assert ShipType.DD == '驱逐'
    assert ShipType.Other == '其他'
    assert ShipType('战列') is ShipType.BB
    assert len(ShipType) == 24
