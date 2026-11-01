"""模块功能：确认主页与每日浮窗的当前层。

上层调用：
- application.ui.navigation：识别当前是否在主页，以及主页上存在的每日浮窗。
- application.ui.navigation.registry：读取浮窗事实与点击落点。

下层依赖：
- common.vision：读取模板事实与模板中心。
- application.ui.template：加载本模块模板。
- application.ui.navigation.types：提供页面契约。
- dispatch.session：读写每日浮窗的处理标记。

边界：只读取一帧、按梯次判层并返回事实，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.ui.navigation.types import PageName
from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template, expect_template_center
from autowsgr.dispatch.session import DailyPopup, get_session


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'navigation/checker/home'

# 本模块的模板文件名；目录小写、文件名全大写。
HOME_MAIN_TEMPLATE = 'HOME_MAIN_720P.png'
NEWS_TEXT_TEMPLATE = 'HOME_NEWS_TEXT_720P.png'
NEWS_CHECKED_TEMPLATE = 'HOME_NEWS_CHECKBOX_CHECKED_720P.png'
NEWS_UNCHECKED_TEMPLATE = 'HOME_NEWS_CHECKBOX_UNCHECKED_720P.png'
REWARD_TEXT_TEMPLATE = 'HOME_REWARD_TEXT_720P.png'
REWARD_CLAIM_TEMPLATE = 'HOME_REWARD_CLAIM_BUTTON_720P.png'
REWARD_CONFIRM_TEMPLATE = 'HOME_REWARD_CONFIRM_BUTTON_720P.png'

# 主页入口图标的归一化区域，校准基准为 1280x720 截图。
HOME_MAIN_ROI = ROI(0.9109, 0.8681, 0.9758, 0.9139)

# 公告浮窗文字区域与勾选框区域。
NEWS_TEXT_ROI = ROI(0.0867, 0.8763, 0.2125, 0.9403)
NEWS_CHECKBOX_ROI = ROI(0.0382, 0.8652, 0.0875, 0.9459)

# 每日奖励浮窗的文字区域与领取按钮区域。
REWARD_TEXT_ROI = ROI(0.1015, 0.268, 0.3313, 0.3362)
REWARD_CLAIM_BUTTON_ROI = ROI(0.4406, 0.6291, 0.5594, 0.7028)

# 每日奖励确认浮窗的确认按钮区域。
REWARD_CONFIRM_BUTTON_ROI = ROI(0.4351, 0.5194, 0.5696, 0.6209)

# 一帧要读的七个模板，顺序固定；解包时的下标顺序以这里为准。
_PROBES: tuple[tuple[str, ROI], ...] = (
    (HOME_MAIN_TEMPLATE, HOME_MAIN_ROI),
    (NEWS_TEXT_TEMPLATE, NEWS_TEXT_ROI),
    (NEWS_CHECKED_TEMPLATE, NEWS_CHECKBOX_ROI),
    (NEWS_UNCHECKED_TEMPLATE, NEWS_CHECKBOX_ROI),
    (REWARD_TEXT_TEMPLATE, REWARD_TEXT_ROI),
    (REWARD_CLAIM_TEMPLATE, REWARD_CLAIM_BUTTON_ROI),
    (REWARD_CONFIRM_TEMPLATE, REWARD_CONFIRM_BUTTON_ROI),
)


# ── 浮窗事实 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HomeNewsOverlay:
    """每日公告浮窗的识别事实。

    Attributes:
        matched: 公告浮窗是否在主页上。
        checked: 公告勾选框状态；已勾选为真、未勾选为假、没有读到勾选框时为空。
    """

    matched: bool
    checked: bool | None


# ── 识别节奏 ────────────────────────────────────────────────────────────────

# 导航确认节奏：从登录页进入要等登录动画与加载，因此给足重试。
_NAV_CONFIRM_ATTEMPTS = 30
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0

# 浮窗识别节奏：浮窗弹出有动画（约 1.5 秒），窗口不够会把「还没弹出来」读成「不在」。
# 5 次 x 0.5 秒，约 2.5 秒，留出余量；命中即返回，浮窗真在时不会白等。
# 回到主页后浮窗可能延迟弹出；等过这段动画再确认主页是干净的。
_POPUP_SETTLE_SECONDS = 2.0

_OVERLAY_ATTEMPTS = 5
_OVERLAY_INTERVAL_SECONDS = 0.5


# ── 当前层 ──────────────────────────────────────────────────────────────────


def read_home_layer(
    ctx: ContextHandle,
    *,
    attempts: int = _OVERLAY_ATTEMPTS,
    interval_seconds: float = _OVERLAY_INTERVAL_SECONDS,
) -> tuple[PageName, ...]:
    """读取当前停在主页的哪几层。

    浮窗是叠在主页上的：确认浮窗压着奖励浮窗、奖励浮窗压着主页、公告遮住整页。
    一次截图把七块模板全部比完，按由深到浅返回能同时看到的层；今天已经处理过的
    浮窗直接跳过，不再参与判定。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足浮窗弹出动画的窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        当前能同时看到的层，由深到浅；一个都没命中时为空元组。
    """
    home, news_text, news_checked, news_unchecked, reward_text, reward_claim, reward_confirm = (
        _read_home_hits(ctx, attempts=attempts, interval_seconds=interval_seconds)
    )
    session = get_session()
    layers: list[PageName] = []
    if reward_confirm and not session.popup_settled(DailyPopup.REWARD_CONFIRM):
        layers.append(PageName.HOME_REWARD_CONFIRM)
    if (reward_text or reward_claim) and not session.popup_settled(DailyPopup.REWARD):
        layers.append(PageName.HOME_REWARD)
    if (news_text or news_checked or news_unchecked) and not session.popup_settled(DailyPopup.NEWS):
        layers.append(PageName.HOME_NEWS)
    if home:
        layers.append(PageName.HOME)
    return tuple(layers)


# ── 页面确认 ────────────────────────────────────────────────────────────────


def popups_all_settled() -> bool:
    """今天的三个每日浮窗是否都已处理。"""
    session = get_session()
    return all(session.popup_settled(popup) for popup in DailyPopup)


def mark_popups_settled(ctx: ContextHandle) -> None:
    """从别的页面回到干净主页时，记下三个浮窗今天都已处理。

    浮窗可能延迟弹出，调用方负责先等过弹出动画；这里只确认主页确实干净后写标记。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
    """
    session = get_session()
    previous = session.current_page()
    if previous is None or previous == PageName.HOME.value:
        return
    if all(session.popup_settled(popup) for popup in DailyPopup):
        return
    if read_home_layer(ctx, attempts=1) != (PageName.HOME,):
        return
    for popup in DailyPopup:
        session.mark_popup_settled(popup)


# ── 浮窗事实读取 ────────────────────────────────────────────────────────────


def read_news_overlay(
    ctx: ContextHandle,
    *,
    attempts: int = _OVERLAY_ATTEMPTS,
    interval_seconds: float = _OVERLAY_INTERVAL_SECONDS,
) -> HomeNewsOverlay:
    """读取每日公告浮窗事实。

    今天已经处理过每日公告时不再识别，直接当它不在。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足浮窗弹出动画的窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        公告浮窗事实：是否在主页上、勾选框状态。
    """
    if get_session().popup_settled(DailyPopup.NEWS):
        return HomeNewsOverlay(matched=False, checked=None)
    _, news_text, news_checked, news_unchecked, _, _, _ = _read_home_hits(
        ctx,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    matched = news_text or news_checked or news_unchecked
    checked = True if news_checked else (False if news_unchecked else None)
    return HomeNewsOverlay(matched=matched, checked=checked)


def check_news_checked(
    ctx: ContextHandle,
    *,
    attempts: int = _OVERLAY_ATTEMPTS,
    interval_seconds: float = _OVERLAY_INTERVAL_SECONDS,
) -> bool:
    """确认每日公告的勾选框是否已经勾上。

    点击勾选框后游戏要过一会儿才更新状态，这里单独读已勾选模板并等它出现。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足点击反馈的窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        勾选框处于已勾选状态时为真。
    """
    return expect_template(
        ctx,
        template=_load_template(NEWS_CHECKED_TEMPLATE),
        roi=NEWS_CHECKBOX_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def check_home_reward_overlay(
    ctx: ContextHandle,
    *,
    attempts: int = _OVERLAY_ATTEMPTS,
    interval_seconds: float = _OVERLAY_INTERVAL_SECONDS,
) -> bool:
    """确认每日奖励浮窗是否在主页上。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足浮窗弹出动画的窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        奖励浮窗存在时为真。"""
    if get_session().popup_settled(DailyPopup.REWARD):
        return False
    # 只等奖励文字或领取按钮出现，范围小，重试才不会被无关模板提前打断。
    result = expect_template(
        ctx,
        template=(
            _load_template(REWARD_TEXT_TEMPLATE),
            _load_template(REWARD_CLAIM_TEMPLATE),
        ),
        roi=(REWARD_TEXT_ROI, REWARD_CLAIM_BUTTON_ROI),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if not result.satisfied:
        return False
    # 确认浮窗盖上来后领取按钮仍在画面里，但当前层已经是确认；奖励层不再算当前。
    return not check_home_reward_confirm(ctx, attempts=1, interval_seconds=0.2)


def check_home_reward_confirm(
    ctx: ContextHandle,
    *,
    attempts: int = _OVERLAY_ATTEMPTS,
    interval_seconds: float = _OVERLAY_INTERVAL_SECONDS,
) -> bool:
    """确认每日奖励确认浮窗是否在主页上。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足浮窗弹出动画的窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        确认浮窗存在时为真。"""
    if get_session().popup_settled(DailyPopup.REWARD_CONFIRM):
        return False
    # 只读确认按钮：和别的模板混在一起时，任一命中会提前返回，等待窗口就失效了。
    return expect_template(
        ctx,
        template=_load_template(REWARD_CONFIRM_TEMPLATE),
        roi=REWARD_CONFIRM_BUTTON_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


# ── 模板中心 ────────────────────────────────────────────────────────────────


def read_news_checkbox_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取每日公告勾选框的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        勾选框模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=(
            _load_template(NEWS_CHECKED_TEMPLATE),
            _load_template(NEWS_UNCHECKED_TEMPLATE),
        ),
        roi=NEWS_CHECKBOX_ROI,
        attempts=1,
    )


def read_reward_claim_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取每日奖励领取按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        领取按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(REWARD_CLAIM_TEMPLATE),
        roi=REWARD_CLAIM_BUTTON_ROI,
        attempts=1,
    )


def read_reward_confirm_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取每日奖励确认按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        确认按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(REWARD_CONFIRM_TEMPLATE),
        roi=REWARD_CONFIRM_BUTTON_ROI,
        attempts=1,
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _read_home_hits(
    ctx: ContextHandle,
    *,
    attempts: int,
    interval_seconds: float,
) -> tuple[bool, ...]:
    """读一帧，返回七个模板各自的命中状态，顺序与 _PROBES 一致。"""
    result = expect_template(
        ctx,
        template=tuple(_load_template(filename) for filename, _ in _PROBES),
        roi=tuple(roi for _, roi in _PROBES),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    return tuple(match.matched for match in result.observation)


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'check_home_reward_confirm',
    'check_home_reward_overlay',
    'check_news_checked',
    'mark_popups_settled',
    'popups_all_settled',
    'read_home_layer',
    'read_news_checkbox_center',
    'read_news_overlay',
    'read_reward_claim_center',
    'read_reward_confirm_center',
]
