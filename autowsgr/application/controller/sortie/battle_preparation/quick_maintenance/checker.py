"""模块功能：识别出征准备页的快速整备状态。

上层调用：
- application.ui.navigation：判断自动补给是否开启、快速修理页签是否激活，并取点击落点。

下层依赖：
- application.ui.template：加载本模块模板。
- common.vision：读取模板匹配事实与命中中心。

边界：只做识别并返回结论，不执行点击、不判断业务是否需要整备、不上报识别错误。
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import (
    ROI,
    Color,
    CompositePixelSignature,
    PixelRule,
    PixelSignature,
    Template,
    expect_ocr,
    expect_pixels,
    expect_template,
    expect_template_center,
)


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'navigation/checker/sortie/battle_preparation/quick_maintenance'

# 左下角自动补给勾选框的开启态；只认开启，勾选框没勾上即视为未开启。
AUTO_SUPPLY_TEMPLATE = 'AUTO_SUPPLY_ON_720P.png'

# 底部功能栏快速修理页签的激活态；页签未激活时与激活模板的相关系数明显低于阈值。
QUICK_REPAIR_TEMPLATE = 'QUICK_REPAIR_ACTIVE_720P.png'

# 修理面板右侧的「全部修理」按钮；页签激活后右侧面板约 1.5-2 秒才联动弹出，
# 只有它出现才说明真的进了修理视图（补给视图的「全部补给」同款同位置，靠模板分不开）。
ALL_REPAIR_BUTTON_TEMPLATE = 'ALL_REPAIR_BUTTON_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720。自动补给勾选框像素范围 [38, 645, 93, 702]，
# 比 54x56 的模板各边大 1px。
AUTO_SUPPLY_ROI = ROI(0.0297, 0.8958, 0.0727, 0.975)

# 快速修理页签像素范围 [469, 538, 651, 590]，比 179x49 的模板各边大 1px。
QUICK_REPAIR_ROI = ROI(0.3664, 0.7472, 0.5086, 0.8194)

# 「全部修理」按钮像素范围 [1022, 464, 1174, 518]，比 151x53 的模板各边大 1px。
ALL_REPAIR_BUTTON_ROI = ROI(0.7984375, 0.64444444, 0.9171875, 0.71944444)

# 修理道具存量文字像素范围 [1136, 398, 1204, 432]；左边界贴着数字前的斜杠右侧，
# 再往左会把斜杠读成数字 1。
REPAIR_STOCK_ROI = ROI(0.8875, 0.55277778, 0.940625, 0.6)


# ── 重试参数 ────────────────────────────────────────────────────────────────

# 页签和「全部修理」按钮要一起命中才算进了修理视图；面板联动有延迟，
# 给四帧、每帧间隔 0.5 秒。
_QUICK_REPAIR_ATTEMPTS = 4
_QUICK_REPAIR_INTERVAL_SECONDS = 0.5


# ── 血条识别数据 ────────────────────────────────────────────────────────────

# 六个物理槽位的血条探针（归一化），取自每条血条左端起 12px 处。
# 校准基准 1280x720：血条像素范围 y 425..434、每条宽 135px，
# x 起点依次为 63 / 212 / 361 / 510 / 659 / 808。
BLOOD_BAR_PROBES = (
    (0.0586, 0.5959),
    (0.1750, 0.5959),
    (0.2915, 0.5959),
    (0.4086, 0.5959),
    (0.5250, 0.5959),
    (0.6415, 0.5959),
)

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
_BLOOD_COLORS: tuple[tuple[ShipDamage, Color], ...] = (
    (ShipDamage.NORMAL, BLOOD_GREEN),
    (ShipDamage.NO_SHIP, BLOOD_NO_SHIP),
    (ShipDamage.MODERATE, BLOOD_YELLOW),
    (ShipDamage.SEVERE, BLOOD_RED_PREPARE),
    (ShipDamage.SEVERE, BLOOD_EMPTY),
)

# 每个槽位一条组合签名：同一探针位上命中任一候选色即成立，命中的候选名就是槽位状态。
# 槽位按物理位置从左到右编号 1-6。
_BLOOD_SIGNATURES = tuple(
    CompositePixelSignature(
        f'slot_{slot}',
        tuple(
            PixelSignature(state.value, (PixelRule(x, y, color),)) for state, color in _BLOOD_COLORS
        ),
    )
    for slot, (x, y) in enumerate(BLOOD_BAR_PROBES, start=1)
)


# ── 状态判断 ────────────────────────────────────────────────────────────────


def check_auto_supply_enabled(ctx: ContextHandle) -> bool:
    """判断左下角的自动补给是否已开启。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        勾选框已勾选时为真；未勾选或识别不到时为假。
    """
    return expect_template(
        ctx,
        template=_load_template(AUTO_SUPPLY_TEMPLATE),
        roi=AUTO_SUPPLY_ROI,
    ).satisfied


def check_quick_repair_active(ctx: ContextHandle) -> bool:
    """判断是否已经进入快速修理视图。

    页签激活和「全部修理」按钮必须同时命中：页签切过去只说明底部面板动了，右侧
    修理面板还有约 1.5-2 秒的联动延迟，按钮出现才代表真的进了修理视图。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        页签与「全部修理」按钮同时命中时为真；任一没命中或识别不到时为假。
    """
    return expect_template(
        ctx,
        template=(
            _load_template(QUICK_REPAIR_TEMPLATE),
            _load_template(ALL_REPAIR_BUTTON_TEMPLATE),
        ),
        roi=(QUICK_REPAIR_ROI, ALL_REPAIR_BUTTON_ROI),
        min_matches=2,
        attempts=_QUICK_REPAIR_ATTEMPTS,
        interval_seconds=_QUICK_REPAIR_INTERVAL_SECONDS,
    ).satisfied


def read_repair_tool_count(ctx: ContextHandle) -> int | None:
    """读取右侧修理面板里的快速修理工具存量。

    面板只在快速修理视图下出现，调用方需要先确认 check_quick_repair_active 成立。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        工具存量；识别不到或识别结果不是纯数字时为 None。
    """
    result = expect_ocr(
        ctx,
        roi=REPAIR_STOCK_ROI,
        allowlist='0123456789',
        attempts=1,
    )
    for detection in result.observation:
        text = detection.recognized_text.strip()
        if text.isdigit():
            return int(text)
    return None


def read_ship_damage(ctx: ContextHandle) -> dict[int, ShipDamage | None]:
    """读取出征准备页六个槽位的血条状态。

    一次识别只截一帧：六个探针位在同一帧上各自命中一个候选色，槽位顺序与画面
    从左到右一致。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        槽位序号（按画面从左到右 1-6）到血条状态的映射；某槽采样色不在参考色范围内
        时为 None。
    """
    result = expect_pixels(ctx, signature=_BLOOD_SIGNATURES, attempts=1)
    return {
        slot: None if match.matched_signature is None else ShipDamage(match.matched_signature)
        for slot, match in enumerate(result.observation, start=1)
    }


# ── 点击落点 ────────────────────────────────────────────────────────────────


def read_auto_supply_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取自动补给勾选框的归一化中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        勾选框模板的命中中心；识别不到时为 None。
    """
    return expect_template_center(
        ctx,
        template=_load_template(AUTO_SUPPLY_TEMPLATE),
        roi=AUTO_SUPPLY_ROI,
    )


def read_quick_repair_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取快速修理页签的归一化中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        页签模板的命中中心；识别不到时为 None。
    """
    return expect_template_center(
        ctx,
        template=_load_template(QUICK_REPAIR_TEMPLATE),
        roi=QUICK_REPAIR_ROI,
    )


def read_all_repair_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取「全部修理」按钮的归一化中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按钮模板的命中中心；识别不到时为 None，由调用方回退静态坐标。
    """
    return expect_template_center(
        ctx,
        template=_load_template(ALL_REPAIR_BUTTON_TEMPLATE),
        roi=ALL_REPAIR_BUTTON_ROI,
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'ALL_REPAIR_BUTTON_ROI',
    'ALL_REPAIR_BUTTON_TEMPLATE',
    'AUTO_SUPPLY_ROI',
    'AUTO_SUPPLY_TEMPLATE',
    'BLOOD_BAR_PROBES',
    'BLOOD_EMPTY',
    'BLOOD_GREEN',
    'BLOOD_NO_SHIP',
    'BLOOD_RED_PREPARE',
    'BLOOD_YELLOW',
    'QUICK_REPAIR_ROI',
    'QUICK_REPAIR_TEMPLATE',
    'REPAIR_STOCK_ROI',
    'TEMPLATE_NAMESPACE',
    'ShipDamage',
    'check_auto_supply_enabled',
    'check_quick_repair_active',
    'read_all_repair_center',
    'read_auto_supply_center',
    'read_quick_repair_center',
    'read_repair_tool_count',
    'read_ship_damage',
]
