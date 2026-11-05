"""模块功能：定义控制器层共用的业务枚举。

上层调用：
- application.controller 各页面包：用 ShipType 表达舰种、用 ShipDamageState 表达
  舰船血量，作为识别结果的分类标签。
- application.vision：舰种识别、血量识别与 OCR 规则输出上述枚举。
- application.fleet_select：按舰种筛选船只、校验阵容规则。
- business.logistics / business.combat：用 RepairMode 表达修理档位、用
  DestroyShipWorkMode 表达拆解口径。

下层依赖：
- common.system.enums：提供统一的中文非法值错误。

边界：只声明跨页面复用的业务枚举，不持有页面坐标、不读取图像、不判断业务规则。
单个页面独占的枚举留在各自模块里，不上提到这里。放这里的唯一理由是「多个层
都要用，但谁也不该拥有它」——放 business 会让 application 反向依赖 business。
"""

from __future__ import annotations

from autowsgr.common.system.enums import IntEnum, StrEnum


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


# ── 舰船血量 ────────────────────────────────────────────────────────────────


class ShipDamageState(IntEnum):
    """舰船血量状态。"""

    NORMAL = 0
    MODERATE = 1
    SEVERE = 2
    NO_SHIP = -1


# ── 修理与拆解口径 ──────────────────────────────────────────────────────────


class RepairMode(IntEnum):
    """修理策略。"""

    moderate_damage = 1
    severe_damage = 2
    repairing = 3


class DestroyShipWorkMode(IntEnum):
    """拆解工作模式。"""

    disable = 0
    include = 1
    exclude = 2


__all__ = [
    'DestroyShipWorkMode',
    'RepairMode',
    'ShipDamageState',
    'ShipType',
]
