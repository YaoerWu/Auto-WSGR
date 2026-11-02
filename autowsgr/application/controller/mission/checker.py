"""模块功能：确认任务页与其领奖浮窗的到达状态。

上层调用：
- application.navigation：确认任务页与「获得」浮窗是否到达或离开，
  以及「全部领取」按钮是否出现。

下层依赖：
- common.vision：读取模板事实。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/mission'

# 本模块的模板文件名；目录小写、文件名全大写。
# 任务页默认落在「全部」页签，因此用它作为页面身份。
ALL_TAB_TEMPLATE = 'MISSION_ALL_TAB_720P.png'
CLAIM_ALL_BUTTON_TEMPLATE = 'MISSION_CLAIM_ALL_720P.png'
REWARD_CONFIRM_BUTTON_TEMPLATE = 'MISSION_REWARD_CONFIRM_720P.png'


# ── 任务页识别区域 ──────────────────────────────────────────────────────────

# 顶部「全部」页签的归一化区域，校准基准为 1280x720 截图。
ALL_TAB_ROI = ROI(0.1477, 0.0223, 0.2204, 0.0848)


# ── 领奖与确认区域 ──────────────────────────────────────────────────────────

# 右下角「全部领取」按钮与「获得」浮窗里的「确认」按钮，同一校准基准。
CLAIM_ALL_BUTTON_ROI = ROI(0.8157, 0.9181, 0.9243, 0.9848)
REWARD_CONFIRM_BUTTON_ROI = ROI(0.4399, 0.6098, 0.554, 0.6889)


# 导航确认节奏：进任务页和弹浮窗都要走完转场，识别不到就重试。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_mission_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在任务页。

    任务页默认落在「全部」页签，因此页面身份用它表达；前识别判到达，后识别判离开。

    领奖浮窗弹出时「全部」页签仍在背后可见，只看页签会在浮窗期间误判到达：
    前识别补一道「领奖浮窗不在」，交给浮窗页表达这一层；后识别只判页签，
    因为「离开任务页」跟浮窗无关。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望离开任务页时为真，默认期望它到达。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    if not expect_template(
        ctx,
        template=_load_template(ALL_TAB_TEMPLATE),
        roi=ALL_TAB_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied:
        return False
    # 后识别只判页签消失，浮窗无关。
    if absent:
        return True
    # 前识别：领奖浮窗还盖着就不算到达任务页。浮窗判定只探当前一帧。
    return not expect_template(
        ctx,
        template=_load_template(REWARD_CONFIRM_BUTTON_TEMPLATE),
        roi=REWARD_CONFIRM_BUTTON_ROI,
        attempts=1,
        interval_seconds=0.5,
    ).satisfied


def check_claim_all_button(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = 1,
    interval_seconds: float = 0.5,
) -> bool:
    """确认「全部领取」按钮是否出现。

    按钮只在有奖励可领时出现在右下角，且不遮挡任务页，所以它不是页面：
    调用方按「先问再做」使用——不在就什么都不做，避免空点。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望按钮不在时为真，默认期望它在。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(CLAIM_ALL_BUTTON_TEMPLATE),
        roi=CLAIM_ALL_BUTTON_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_mission_reward_confirm(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认「获得」浮窗是否弹出。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望确认浮窗不在时为真，默认期望它弹出。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(REWARD_CONFIRM_BUTTON_TEMPLATE),
        roi=REWARD_CONFIRM_BUTTON_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'check_claim_all_button',
    'check_mission_page',
    'check_mission_reward_confirm',
]
