"""模块功能：出征准备页舰队识别的识别区域、参考色与槽位落点。

上层调用：
- application.controller.sortie.battle_preparation.ship_recognition.checker：读取识别区域与签名。
- application.controller.sortie.battle_preparation.ship_recognition.page：读取槽位落点。

下层依赖：
- common.vision：提供识别区域、像素颜色与像素签名类型。

边界：只保存本包的静态校准数据，不保存文字规则、不保存业务规则、不发起识别与点击。
"""

from __future__ import annotations

from enum import StrEnum

from autowsgr.common.vision import (
    ROI,
    Color,
    CompositePixelSignature,
    PixelRule,
    PixelSignature,
)


# 出征准备页的六个物理槽位。校准基准 1280x720：槽左边界依次为
# 63 / 212 / 361 / 510 / 659 / 808，卡片宽 135px、槽间距 149px。
FLEET_SLOT_COUNT = 6


# ── 舰名识别区域 ────────────────────────────────────────────────────────────

# 舰名行像素范围 y 438..457，逐槽取满卡片宽度。逐槽直读比「整条横带 OCR 再按检测框
# 中心归槽」简单，也不会因为识别框偏左偏右把舰名分到相邻槽位。
SHIP_NAME_ROIS = (
    ROI(0.0493, 0.6084, 0.1547, 0.6348),
    ROI(0.1657, 0.6084, 0.2711, 0.6348),
    ROI(0.2821, 0.6084, 0.3875, 0.6348),
    ROI(0.3985, 0.6084, 0.5040, 0.6348),
    ROI(0.5149, 0.6084, 0.6204, 0.6348),
    ROI(0.6313, 0.6084, 0.7368, 0.6348),
)


# ── 舰种识别区域 ────────────────────────────────────────────────────────────

# 舰种行像素范围 y 380..409，每槽取槽左边界右侧 2px 起的 46px 窄框。
# 不含右侧国籍括号，识别结果直接是「轻母」这样的枚举值。
SHIP_TYPE_ROIS = (
    ROI(0.0508, 0.5278, 0.0868, 0.5681),
    ROI(0.1672, 0.5278, 0.2032, 0.5681),
    ROI(0.2836, 0.5278, 0.3196, 0.5681),
    ROI(0.4000, 0.5278, 0.4360, 0.5681),
    ROI(0.5165, 0.5278, 0.5524, 0.5681),
    ROI(0.6329, 0.5278, 0.6688, 0.5681),
)


# ── 等级识别区域 ────────────────────────────────────────────────────────────

# 等级行像素范围 y 408..423，每槽取槽左边界右侧 2px 起的 57px 窄框。
# 不含右侧星级，识别结果形如「LV.110」。
SHIP_LEVEL_ROIS = (
    ROI(0.0508, 0.5667, 0.0954, 0.5875),
    ROI(0.1672, 0.5667, 0.2118, 0.5875),
    ROI(0.2836, 0.5667, 0.3282, 0.5875),
    ROI(0.4000, 0.5667, 0.4446, 0.5875),
    ROI(0.5165, 0.5667, 0.5610, 0.5875),
    ROI(0.6329, 0.5667, 0.6774, 0.5875),
)


# ── 血条识别区域 ────────────────────────────────────────────────────────────

# 六个物理槽位的血条探针（归一化），取自每条血条左端起 12px 处。
# 校准基准 1280x720：血条像素范围 y 425..434、每条宽 135px，
# x 起点依次为 63 / 212 / 361 / 510 / 659 / 808。
BLOOD_BAR_PROBES = (
    (0.0586, 0.5959),
    (0.1750, 0.5959),
    (0.2915, 0.5959),
    (0.4079, 0.5959),
    (0.5243, 0.5959),
    (0.6407, 0.5959),
)


# ── 血条参考色 ──────────────────────────────────────────────────────────────

# 血条参考色（RGB），按实机画面标定。血条按长度表示血量、整条同色，从左到右依次
# 是满血绿、中破黄、大破橙红，血量耗尽后残留深灰；取血条左端就是当前状态色。
# scrcpy 解码后的颜色比静态截图暗，旧框架用静态图标定的绿色偏亮约 20，实机会落在
# 容差外，因此这里用实机帧重新标定。
BLOOD_GREEN = Color(63, 151, 113)  # 正常
BLOOD_YELLOW = Color(239, 172, 32)  # 中破
BLOOD_RED_PREPARE = Color(234, 102, 36)  # 大破（准备页）
BLOOD_EMPTY = Color(58, 60, 62)  # 血条耗尽
BLOOD_NO_SHIP = Color(43, 87, 112)  # 空槽

# TODO: 血条容差 V1 统一沿用默认值 NUMPY_DEFAULT_PIXEL_TOLERANCE（30.0），先保守上线。
# 实机只采到满血绿、中破黄、大破橙红三态，空灰与空槽两态还没有实机样本，因此不按
# 参考色分项设容差。若后续出现误判，改成逐色 PixelRule(tolerance=...)：满血绿可放宽
# 到 40（距空槽蓝 67.1、实测最差样本偏 22），中破黄与大破红可到 35（两者相距 70.3），
# 空灰与空槽必须收到 25（两者参考色只差 58.8，统一 30 已轻微重叠）。


# ── 血条状态 ────────────────────────────────────────────────────────────────


class ShipDamage(StrEnum):
    """出征准备页单个槽位的血条状态。"""

    NO_SHIP = 'no_ship'
    NORMAL = 'normal'
    MODERATE = 'moderate'
    SEVERE = 'severe'


# 参考色到槽位状态的映射，按判定顺序排列；组合签名命中第一个成立的候选就停。
BLOOD_STATES: tuple[tuple[ShipDamage, Color], ...] = (
    (ShipDamage.NORMAL, BLOOD_GREEN),
    (ShipDamage.NO_SHIP, BLOOD_NO_SHIP),
    (ShipDamage.MODERATE, BLOOD_YELLOW),
    (ShipDamage.SEVERE, BLOOD_RED_PREPARE),
    (ShipDamage.SEVERE, BLOOD_EMPTY),
)

# 每个槽位一条组合签名：同一探针位上命中任一候选色即成立，命中的候选名就是槽位状态。
# 槽位按物理位置从左到右编号 1-6。
BLOOD_SIGNATURES = tuple(
    CompositePixelSignature(
        f'slot_{slot}',
        tuple(
            PixelSignature(state.value, (PixelRule(x, y, color),)) for state, color in BLOOD_STATES
        ),
    )
    for slot, (x, y) in enumerate(BLOOD_BAR_PROBES, start=1)
)


# ── 槽位点击落点 ────────────────────────────────────────────────────────────

# 六个槽位卡片中心的归一化坐标，校准基准 1280x720。x 取卡片横向中心
# （槽左边界 63 / 212 / 361 / 510 / 659 / 808 加半个卡宽 67.5），
# y 取卡片上半部 0.4625，避开底部的血条与舰名。
CLICK_SHIP_SLOTS = (
    (0.1020, 0.4625),
    (0.2184, 0.4625),
    (0.3348, 0.4625),
    (0.4512, 0.4625),
    (0.5676, 0.4625),
    (0.6840, 0.4625),
)

# 拖拽一艘舰船到另一个槽位的滑动时长，太短会被游戏当成点按。
DRAG_DURATION_SECONDS = 0.5


__all__ = [
    'BLOOD_BAR_PROBES',
    'BLOOD_EMPTY',
    'BLOOD_GREEN',
    'BLOOD_NO_SHIP',
    'BLOOD_RED_PREPARE',
    'BLOOD_SIGNATURES',
    'BLOOD_STATES',
    'BLOOD_YELLOW',
    'CLICK_SHIP_SLOTS',
    'DRAG_DURATION_SECONDS',
    'FLEET_SLOT_COUNT',
    'SHIP_LEVEL_ROIS',
    'SHIP_NAME_ROIS',
    'SHIP_TYPE_ROIS',
    'ShipDamage',
]
