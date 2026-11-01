"""模块功能：定义船只识别的舰种与识别域枚举。

上层调用：
- application.ui.ships：各识别域与入口用这里定义的枚举表达舰种和路由。
- business：按舰种筛选船只、校验阵容规则。

下层依赖：
- common.system.enums：提供统一的中文非法值错误。

边界：只声明枚举，不持有识别坐标、不读取图像、不判断业务规则。
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


# ── 识别域 ──────────────────────────────────────────────────────────────────


class ShipTaskType(StrEnum):
    """船只识别按任务类型划分的识别域。"""

    EXERCISE = 'exercise'


__all__ = ['ShipTaskType', 'ShipType']
