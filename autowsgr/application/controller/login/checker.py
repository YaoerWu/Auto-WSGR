"""模块功能：提供登录流程各画面的识别入口。

上层调用：
- application.navigation：把登录相关画面注册为导航器的到达确认；
- application.navigation.service：启动流程按顺序判断当前画面。

下层依赖：
- common.vision：读取模板与 OCR 事实。

边界：只暴露画面判断与区服定位，不做点击、导航或启动编排。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import (
    ROI,
    Template,
    expect_ocr,
    expect_template,
    expect_template_center,
)


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui.login')


# ── 识别模板 ────────────────────────────────────────────────────────────────

# 模板目录名，对应 resources/image/application/controller/login/。
TEMPLATE_NAMESPACE = 'controller/login'

# 健康游戏提示的黑屏画面，全屏模板。
BLACK_SCREEN_TEMPLATE = 'LOGIN_BLACK_SCREEN_720P.png'

# 登录页的进入游戏按钮。
ENTER_BUTTON_TEMPLATE = 'LOGIN_ENTER_BUTTON_720P.png'

# 登录页的点击换区文字。
SWITCH_ENTRY_TEMPLATE = 'SERVER_SWITCH_ENTRY_720P.png'

# 区服选择页的切换大区按钮。
SWITCH_SERVER_TEMPLATE = 'SERVER_SWITCH_BUTTON_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 更新提示文字区域。
UPDATE_PROMPT_ROI = ROI(0.3211, 0.3681, 0.4859, 0.4222)

# 更新中与加载中的进度文字区域，两个画面共用同一条横幅。
PROGRESS_TEXT_ROI = ROI(0.3867, 0.8389, 0.6125, 0.8986)

# 进入游戏按钮区域。
ENTER_BUTTON_ROI = ROI(0.8195, 0.8236, 0.9532, 0.9098)

# 点击换区文字区域。
SWITCH_ENTRY_ROI = ROI(0.6820, 0.6958, 0.7844, 0.7653)

# 切换大区按钮区域。
SWITCH_SERVER_ROI = ROI(0.8133, 0.8792, 0.9407, 0.9667)

# 四个区服条目区域，顺序与区服列表从上到下一致。
SERVER_NAME_ROIS = (
    ROI(0.7836, 0.0389, 0.8984, 0.1194),
    ROI(0.7852, 0.1972, 0.8961, 0.2708),
    ROI(0.7883, 0.3583, 0.8977, 0.4292),
    ROI(0.7867, 0.5097, 0.9000, 0.5847),
)


# ── OCR 期望文本 ────────────────────────────────────────────────────────────

UPDATE_PROMPT_TEXT = '有新的内容需要更新'
LOADING_TEXT = '正在进入港区'
SERVER_NAMES = ('胡德', '俾斯麦', '昆西', '长春')


# 导航确认节奏：点击后要等弹层动画，单帧会立刻判失败。
_NAV_CONFIRM_ATTEMPTS = 10
_NAV_CONFIRM_INTERVAL_SECONDS = 0.5


def check_black_screen(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = 1,
    interval_seconds: float = 0.5,
) -> bool:
    """确认是否停留在健康游戏提示画面。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望条件取反时为真，默认期望原始条件成立。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(BLACK_SCREEN_TEMPLATE),
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_update_prompt(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = 1,
    interval_seconds: float = 0.5,
) -> bool:
    """确认是否出现需要更新的提示。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望条件取反时为真，默认期望原始条件成立。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_ocr(
        ctx,
        expect=UPDATE_PROMPT_TEXT,
        roi=UPDATE_PROMPT_ROI,
        recognition_profile='single_line',
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_loading(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = 1,
    interval_seconds: float = 0.5,
) -> bool:
    """确认是否正在加载（"正在进入港区"）。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望条件取反时为真，默认期望原始条件成立。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_ocr(
        ctx,
        expect=LOADING_TEXT,
        roi=PROGRESS_TEXT_ROI,
        recognition_profile='single_line',
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_login_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在登录页。

    进入游戏按钮与点击换区文字**二选一命中**即视为在登录页。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望条件取反时为真，默认期望原始条件成立。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=(
            _load_template(ENTER_BUTTON_TEMPLATE),
            _load_template(SWITCH_ENTRY_TEMPLATE),
        ),
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_server_select(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """确认是否在区服选择页。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望条件取反时为真，默认期望原始条件成立。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        断言满足时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(SWITCH_SERVER_TEMPLATE),
        roi=SWITCH_SERVER_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def get_server_index(name: str) -> int:
    """返回区服名在登录列表中的固定位置。

    区服列表固定不滚动，位置是静态映射；OCR 定位失败时用它兜底。

    Args:
        name: 区服名，取值见 `SERVER_NAMES`。

    Returns:
        位置序号（0 起）。

    Raises:
        ValueError: 名字不在区服列表内。
    """
    return SERVER_NAMES.index(name)


def read_server_position(ctx: ContextHandle, name: str) -> int | None:
    """查找目标区服在列表中的位置。

    区服列表固定不滚动，因此拿目标区服名依次比对四条区域即可。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        name: 目标区服名。

    Returns:
        位置序号（0 起），未命中时返回 None。
    """
    for index, roi in enumerate(SERVER_NAME_ROIS):
        if expect_ocr(
            ctx, expect=name, roi=roi, recognition_profile='single_line', attempts=1
        ).satisfied:
            _log.info('[UI] 登录识别 → 区服定位：name={!r}，position={}', name, index)
            return index
    _log.warning('[UI] 登录识别 → 区服定位失败：name={!r}', name)
    return None


def read_server_index(ctx: ContextHandle, name: str) -> int:
    """把区服名换成它在列表中的固定位置，供导航点击区服条目使用。

    位置由 OCR 逐条比对得出；读不到时退回静态映射，保证换区链路不会因为一次识别失败而中断。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        name: 目标区服名，取值见 `SERVER_NAMES`。

    Returns:
        区服在列表中的位置序号（0 起）。
    """
    index = read_server_position(ctx, name)
    if index is None:
        index = get_server_index(name)
        _log.warning('[UI] 登录识别 → 区服定位兜底：server={!r}，position={}', name, index)
    return index


def read_enter_button_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取登录页"进入游戏"按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按钮模板命中时的归一化中心；未命中时为 None。
    """
    return expect_template_center(
        ctx, template=_load_template(ENTER_BUTTON_TEMPLATE), roi=ENTER_BUTTON_ROI, attempts=1
    )


def read_switch_entry_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取登录页"点击换区"入口的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        入口模板命中时的归一化中心；未命中时为 None。
    """
    return expect_template_center(
        ctx, template=_load_template(SWITCH_ENTRY_TEMPLATE), roi=SWITCH_ENTRY_ROI, attempts=1
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'check_black_screen',
    'check_loading',
    'check_login_page',
    'check_server_select',
    'check_update_prompt',
    'get_server_index',
    'read_enter_button_center',
    'read_server_index',
    'read_server_position',
    'read_switch_entry_center',
]
