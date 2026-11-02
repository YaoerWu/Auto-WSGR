"""模块功能：确认后院主页并读取四个入口的点击中心。

上层调用：
- application.ui.navigation：确认后院主页是否到达或离开，读取四个入口的点击中心。

下层依赖：
- common.vision：读取模板事实与模板中心。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
四个二级页的确认入口各在自己的子包里。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template, expect_template_center


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间；四个入口模板都放在这个根目录下。
TEMPLATE_NAMESPACE = 'controller/backyard'


# ── 后院主页身份 ────────────────────────────────────────────────────────────

# 后院主页没有专属模板：四个入口同一时刻出现，任选其一当身份即可，这里取浴室入口。
BACKYARD_TEMPLATE = 'BACKYARD_BATH_ENTRY_720P.png'
BACKYARD_ROI = ROI(0.2446, 0.3, 0.3524, 0.4167)


# ── 四个入口（点击落点用） ──────────────────────────────────────────────────

CANTEEN_ENTRY_TEMPLATE = 'BACKYARD_CANTEEN_ENTRY_720P.png'
ACADEMY_ENTRY_TEMPLATE = 'BACKYARD_ACADEMY_ENTRY_720P.png'
RANK_ROOM_ENTRY_TEMPLATE = 'BACKYARD_RANK_ROOM_ENTRY_720P.png'
BATH_ENTRY_TEMPLATE = 'BACKYARD_BATH_ENTRY_720P.png'

CANTEEN_ENTRY_ROI = ROI(0.7485, 0.5764, 0.8758, 0.7487)
ACADEMY_ENTRY_ROI = ROI(0.8641, 0.3473, 0.9696, 0.4695)
RANK_ROOM_ENTRY_ROI = ROI(0.6493, 0.1514, 0.7532, 0.2362)
BATH_ENTRY_ROI = ROI(0.2446, 0.3, 0.3524, 0.4167)


# 进后院有较长的切换动画，到达确认给足重试（等效 5 秒缓冲，用户确认不用 sleep）。
_BACKYARD_ENTRY_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_backyard_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _BACKYARD_ENTRY_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在后院主页。

    后院主页没有专属模板，拿四个入口里的任意一个当身份；前识别判到达，后识别判离开。
    离开判定天然成立：进二级页时整页被换掉，入口模板自然消失。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望离开后院主页时为真，默认期望它到达。
        attempts: 识别次数，默认按进后院的节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(BACKYARD_TEMPLATE),
        roi=BACKYARD_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def read_canteen_entry_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取餐厅入口模板命中的中心，供导航器点击。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        入口模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(CANTEEN_ENTRY_TEMPLATE),
        roi=CANTEEN_ENTRY_ROI,
        attempts=1,
    )


def read_academy_entry_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取学院入口模板命中的中心，供导航器点击。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        入口模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(ACADEMY_ENTRY_TEMPLATE),
        roi=ACADEMY_ENTRY_ROI,
        attempts=1,
    )


def read_rank_room_entry_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取军阶室入口模板命中的中心，供导航器点击。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        入口模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(RANK_ROOM_ENTRY_TEMPLATE),
        roi=RANK_ROOM_ENTRY_ROI,
        attempts=1,
    )


def read_bath_entry_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取浴室入口模板命中的中心，供导航器点击。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        入口模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(BATH_ENTRY_TEMPLATE),
        roi=BATH_ENTRY_ROI,
        attempts=1,
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'check_backyard_page',
    'read_academy_entry_center',
    'read_bath_entry_center',
    'read_canteen_entry_center',
    'read_rank_room_entry_center',
]
