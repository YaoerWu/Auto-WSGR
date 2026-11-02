"""模块功能：定义控制器层共用的业务枚举。

上层调用：
- application.controller 各页面包：用 ShipType 表达舰种，作为识别结果的分类标签。
- application.fleet_select：按舰种筛选船只、校验阵容规则。

下层依赖：
- common.system.enums：提供统一的中文非法值错误。

边界：只声明跨页面复用的业务枚举，不持有页面坐标、不读取图像、不判断业务规则。
单个页面独占的枚举留在各自模块里，不上提到这里。
"""

from __future__ import annotations

from autowsgr.common.system.enums import StrEnum


# ── 舰船类型 ────────────────────────────────────────────────────────────────


class ShipType(StrEnum):
    """舰船类型，成员值即游戏内显示的舰种名称。"""

    CV = '航母'
    CVL = '轻母'
    AV = '装母'
    BB = '战列'
    BBV = '航战'
    BC = '战巡'
    CA = '重巡'
    CAV = '航巡'
    CLT = '雷巡'
    CL = '轻巡'
    BM = '重炮'
    DD = '驱逐'
    SSG = '导潜'
    SS = '潜艇'
    SC = '炮潜'
    NAP = '补给'
    ASDG = '导驱'
    AADG = '防驱'
    KP = '导巡'
    CG = '防巡'
    CBG = '大巡'
    BG = '防战'
    BBG = '导战'
    Other = '其他'


__all__ = ['ShipType']
