"""模块功能：确认普通推图活动的页面状态并读取识别事实。

上层调用：
- application.ui.navigation：确认首页活动入口、活动地图状态与出征准备前置页，
  并读取任务绑定的活动玩法与章节。

下层依赖：
- common.vision：读取模板与 OCR 事实。
- application.ui.template：加载本活动模板。
- application.ui.navigation.types：提供导航错误。

边界：只识别、解析并返回活动事实，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from autowsgr.application.ui.navigation.types import NavigationError
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
    from collections.abc import Sequence

    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('ui')


# ── 本期活动识别数据 ────────────────────────────────────────────────────────

# 活动标识与本期期号；换期改期号，并按 <活动>_<期号> 补一份模板目录。
ACTIVITY = 'stage_push'
PERIOD = '20260930'

# 本活动在 UI 模板根下的命名空间：一期一个目录，换期换目录。
TEMPLATE_NAMESPACE = f'navigation/checker/event/{ACTIVITY}_{PERIOD}'

# 本活动的模板文件名。
HOME_ENTRY_TEMPLATE = 'EVENT_HOME_ENTRY_720P.png'
MODE_NORMAL_TEMPLATE = 'EVENT_MODE_NORMAL_720P.png'
MODE_HARD_TEMPLATE = 'EVENT_MODE_HARD_720P.png'
SORTIE_PREPARE_TEMPLATE = 'EVENT_SORTIE_PREPARE_720P.png'

# 校准值以 1280x720 截图为基准换算为归一化区域。
HOME_ENTRY_ROI = ROI(0.8546, 0.3222, 0.9883, 0.6834)
# 地图页左下角模式按钮；按钮文字表示"要切换到的"模式，命中它说明当前在另一种难度。
MODE_ROI = ROI(0.0101, 0.9, 0.1118, 0.932)
# 地图标题区域，普通地图与困难地图的名称不同。
MAP_NAME_ROI = ROI(0.4023, 0.0291, 0.5954, 0.0723)
# 节点浮窗内的出击准备按钮，命中即说明节点浮窗已经打开。
SORTIE_PREPARE_ROI = ROI(0.7882, 0.8166, 0.925, 0.882)
# 节点浮窗左上角的关卡标题，干净地图页该区域没有文字。
STAGE_TITLE_ROI = ROI(0.0273, 0.0625, 0.2079, 0.1084)


# ── 本期活动识别期望 ────────────────────────────────────────────────────────

# 地图名与关卡名，换期只改这一段。困难模式的标题在本名后追加"困难"二字；
# 括号形态不稳定，因此不参与比对，只判"标题 + 困难"。
_MAP_NAME = '最强之舟'
_STAGE_NAMES = {
    1: '天降火雨',
    2: '鹰群出击',
    3: '追逐跳跃',
    4: '火力全开',
    5: '四面合围',
    6: '海空鏖战',
}

# 只读探测只取当前一帧，不等待目标出现。
_PROBE_ATTEMPTS = 1
# 困难模式的固定标记；实测标题括号有全角、半角和丢失三种形态，因此只判这两个字。
_HARD_MARKER = '困难'
# 标题归一化时丢弃的装饰字符，保留数字、字母和汉字。
_TITLE_DECORATION = re.compile(r'[^0-9a-zA-Z一-鿿]+')
# 归一化标题里的关卡编号形式，大小写不敏感。
_STAGE_TITLE_PATTERN = re.compile(r'ex(\d+)')


# ── 活动页面事实模型 ────────────────────────────────────────────────────────


class EventMode(StrEnum):
    """活动地图难度。"""

    NORMAL = 'normal'
    HARD = 'hard'


@dataclass(frozen=True, slots=True)
class EventMapState:
    """活动地图页面的事实与结论。

    Attributes:
        on_clean_map: 当前是否为没有节点浮窗的干净地图页。
        button_mode: 模式按钮显示的模式，即点击后要切换到的难度；没有按钮时为空。
        title_mode: 地图标题对应的难度；没有读到标题时为空。
        current_mode: 由按钮和标题推出的当前难度；浮窗态、矛盾或读不到时为空。
    """

    on_clean_map: bool
    button_mode: EventMode | None
    title_mode: EventMode | None
    current_mode: EventMode | None


@dataclass(frozen=True, slots=True)
class EventStage:
    """活动章节的执行参数。

    Attributes:
        difficulty: 章节难度。
        node: 章节在地图上的落点序号。
    """

    difficulty: EventMode
    node: int


# ── 章节解析 ────────────────────────────────────────────────────────────────

# 地图上的落点数量；普通与困难共用同一组落点。
_NODE_COUNT = 6


def parse_stage(stage: str) -> EventStage:
    """把任务里的章节标识解析成执行参数。

    支持任务契约的 EX1-EX12，以及旧控制器的 E1-E6 / H1-H6 写法。

    Args:
        stage: 章节标识。

    Returns:
        章节的执行参数：难度与落点序号。

    Raises:
        ValueError: 标识格式非法或超出范围。
    """
    # 1. 先换算成跨难度的全局编号：EX1-EX12 直接取数字，E1-E6 / H1-H6 按难度偏移。
    text = stage.strip().upper()
    legacy = len(text) == 2 and text[0] in ('E', 'H')
    if text.startswith('EX'):
        digits = text[2:]
    elif legacy:
        digits = text[1:]
    else:
        raise ValueError(f'无效的章节标识: {stage!r}')
    if not digits.isdigit():
        raise ValueError(f'无效的章节标识: {stage!r}')

    number = int(digits)
    if legacy:
        if not 1 <= number <= _NODE_COUNT:
            raise ValueError(f'章节标识超出范围: {stage!r}')
        if text[0] == 'H':
            number += _NODE_COUNT
    elif not 1 <= number <= _NODE_COUNT * 2:
        raise ValueError(f'章节标识超出范围: {stage!r}')

    # 2. 编号在后半段的是困难；落点序号按节点数取模回到 1-6。
    difficulty = EventMode.NORMAL if number <= _NODE_COUNT else EventMode.HARD
    return EventStage(difficulty=difficulty, node=(number - 1) % _NODE_COUNT + 1)


# ── 标题解析 ────────────────────────────────────────────────────────────────


def is_stage_title_matched(title_texts: Sequence[str], *, node: int, hard: bool) -> bool:
    """判断关卡标题是否指向目标章节。

    模式一致，且编号或名称任一命中即算匹配。

    Args:
        title_texts: 关卡标题的识别文本。
        node: 目标章节在地图上的落点序号，1 到 6。
        hard: 目标章节是否属于困难模式。

    Returns:
        标题命中目标章节时为真。
    """
    stage_name = _STAGE_NAMES[node]
    stage_number = node + (len(_STAGE_NAMES) if hard else 0)
    for text in title_texts:
        normalized = _TITLE_DECORATION.sub('', text).lower()
        # 普通与困难共用同一批章节名，只有"困难"二字能区分两者：模式不符直接排除，
        # 否则同名困难章节会被普通章节的判据抢先命中。
        if (_HARD_MARKER in normalized) != hard:
            continue
        # 关卡编号和章节名称任一命中即算匹配，兼容标题编号被 OCR 丢字的情况。
        matched = _STAGE_TITLE_PATTERN.match(normalized)
        if (int(matched.group(1)) if matched else None) == stage_number:
            return True
        if stage_name in normalized:
            return True
    return False


def calculate_current_mode(
    button_mode: EventMode | None,
    title_mode: EventMode | None,
) -> EventMode | None:
    """由模式按钮和地图标题推出当前难度。

    Args:
        button_mode: 模式按钮读出的难度。
        title_mode: 地图标题读出的难度。

    Returns:
        两者一致指向的难度；证据矛盾或都读不到时为空。
    """
    # 1. 按钮和标题互为反向证据时，两者一致指向同一种当前难度。
    if button_mode is EventMode.NORMAL and title_mode is EventMode.HARD:
        return EventMode.HARD
    if button_mode is EventMode.HARD and title_mode is EventMode.NORMAL:
        return EventMode.NORMAL

    # 2. 没有按钮说明困难难度尚未开放，此时只可能是普通地图。
    if button_mode is None and title_mode is EventMode.NORMAL:
        return EventMode.NORMAL

    # 3. 其余组合是矛盾或读不到，结论交给调用方判断。
    return None


# ── 识别入口 ────────────────────────────────────────────────────────────────


def read_mode_button(
    ctx: ContextHandle,
    *,
    attempts: int = _PROBE_ATTEMPTS,
    interval_seconds: float = 0.5,
) -> EventMode | None:
    """读取模式按钮显示的模式。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        模式按钮指向的难度；两张模板都没命中时为空。
    """
    result = expect_template(
        ctx,
        template=(
            _load_template(MODE_NORMAL_TEMPLATE),
            _load_template(MODE_HARD_TEMPLATE),
        ),
        roi=MODE_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    normal_match, hard_match = result.observation
    if normal_match.matched:
        return EventMode.NORMAL
    if hard_match.matched:
        return EventMode.HARD
    return None


def read_map_title(
    ctx: ContextHandle,
    *,
    attempts: int = _PROBE_ATTEMPTS,
    interval_seconds: float = 0.5,
) -> EventMode | None:
    """读取地图标题并判断难度。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        地图标题对应的难度；读不到时为空。
    """
    result = expect_ocr(
        ctx,
        expect=(_MAP_NAME, f'{_MAP_NAME}（困难）'),
        roi=MAP_NAME_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    title_texts = [detection.recognized_text for detection in result.observation]
    # 困难标记是困难模式独有的文字，先判它，避免名称前缀被普通地图名抢先命中。
    if any(_HARD_MARKER in text for text in title_texts):
        return EventMode.HARD
    if any(_MAP_NAME in text for text in title_texts):
        return EventMode.NORMAL
    return None


def read_stage_title_texts(ctx: ContextHandle) -> list[str]:
    """读取关卡标题文本。

    标题由"EX+编号+名称"组成，无法用固定文本等待，因此用候选集合触发一次读取后自行判定。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        关卡标题的识别文本。
    """
    result = expect_ocr(
        ctx,
        expect=tuple(_STAGE_NAMES.values()),
        roi=STAGE_TITLE_ROI,
        attempts=_PROBE_ATTEMPTS,
    )
    return [
        detection.recognized_text
        for detection in result.observation
        if any(name in detection.recognized_text for name in _STAGE_NAMES.values())
        # 只读到编号、没读到名称的标题同样有效，不能在这一步丢掉。
        or _STAGE_TITLE_PATTERN.search(detection.recognized_text.lower())
    ]


def read_sortie_overlay(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _PROBE_ATTEMPTS,
    interval_seconds: float = 0.5,
) -> bool:
    """判断节点浮窗当前是否已经打开。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        浮窗已经打开时为真。
    """
    result = expect_template(
        ctx,
        template=_load_template(SORTIE_PREPARE_TEMPLATE),
        roi=SORTIE_PREPARE_ROI,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if absent:
        return result.satisfied
    # 浮窗打开时关卡标题才出现，用标题文字补强模板判据。
    return result.satisfied or bool(read_stage_title_texts(ctx))


def read_mode_button_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取模式按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        模式按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=(
            _load_template(MODE_NORMAL_TEMPLATE),
            _load_template(MODE_HARD_TEMPLATE),
        ),
        roi=MODE_ROI,
        attempts=_PROBE_ATTEMPTS,
    )


def read_sortie_prepare_center(ctx: ContextHandle) -> tuple[float, float] | None:
    """读取节点浮窗内"确认出征"按钮的中心。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按钮模板命中时的归一化中心；未命中时为空。
    """
    return expect_template_center(
        ctx,
        template=_load_template(SORTIE_PREPARE_TEMPLATE),
        roi=SORTIE_PREPARE_ROI,
        attempts=_PROBE_ATTEMPTS,
    )


# ── 页面判断 ────────────────────────────────────────────────────────────────

# 导航确认节奏：进出这一页要走完动画与加载，因此给足重试；只做页面定位的调用方
# 可以显式传更小的 attempts 只探一帧。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


def check_event_map_page(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
    event_type: str | None = None,
) -> bool:
    """确认当前是否在活动地图页。

    判断标准：模式按钮模板命中任意一张。浮窗会压暗整页、让两张按钮模板一起失效，
    因此"按钮还亮着"同时说明页面干净；地图标题只作参考，读不到不算失败。
    省略 event_type 时只判页面身份，供导航器定位当前页使用。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望地图标志消失时为真，默认期望它出现。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。
        event_type: 活动玩法标识；提供时校验调用方选对了 checker。

    Returns:
        断言满足时为真。

    Raises:
        ValueError: 活动玩法标识与当前 checker 不一致。
    """
    if event_type is not None:
        _require_activity(event_type)
    button_mode = read_mode_button(ctx, attempts=attempts, interval_seconds=interval_seconds)
    # 按钮不命中时，要么是浮窗压着，要么是困难尚未开放——只有后者还是活动地图页，
    # 用"没有浮窗 + 地图名是普通名"补上这一种。
    open_map = button_mode is not None or (
        read_map_title(ctx) is EventMode.NORMAL and not read_sortie_overlay(ctx)
    )
    return open_map != absent


def check_event_entry(ctx: ContextHandle, *, event_type: str) -> bool:
    """确认首页活动入口卡片是否可见。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        event_type: 活动玩法标识，用于确认调用方选对了 checker。

    Returns:
        入口模板命中时为真；读不到时为假。
    """
    _require_activity(event_type)
    result = expect_template(
        ctx,
        template=_load_template(HOME_ENTRY_TEMPLATE),
        roi=HOME_ENTRY_ROI,
    )
    return result.satisfied


def read_event_map_state(
    ctx: ContextHandle,
    *,
    attempts: int = _PROBE_ATTEMPTS,
    interval_seconds: float = 0.5,
    event_type: str | None = None,
) -> EventMapState:
    """读取活动地图页面的难度事实并给出当前难度。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认只探测当前一帧。
        interval_seconds: 两次识别之间的等待秒数。
        event_type: 活动玩法标识；提供时校验调用方选对了 checker。

    Returns:
        活动地图页面事实；浮窗态、矛盾或读不到时结论为空。

    Raises:
        ValueError: 活动玩法标识与当前 checker 不一致。
    """
    if event_type is not None:
        _require_activity(event_type)

    # 1. 分别读取模式按钮和地图标题，两者都是当前难度的独立证据。
    button_mode = read_mode_button(ctx, attempts=attempts, interval_seconds=interval_seconds)
    title_mode = read_map_title(ctx, attempts=attempts, interval_seconds=interval_seconds)

    # 2. 浮窗会压暗整页并让模式按钮模板失效，因此浮窗态不下难度结论。
    on_clean_map = not read_sortie_overlay(ctx)

    state = EventMapState(
        on_clean_map=on_clean_map,
        button_mode=button_mode,
        title_mode=title_mode,
        current_mode=calculate_current_mode(button_mode, title_mode) if on_clean_map else None,
    )
    _log.debug(
        '[UI] 活动地图 → 读状态：on_clean_map={!r}，current_mode={!r}',
        state.on_clean_map,
        state.current_mode,
    )
    return state


def wait_event_mode(
    ctx: ContextHandle,
    *,
    event_type: str,
    mode: EventMode,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """等地图难度变成目标难度。

    切换本身很快，但画面稳定之前模式按钮和地图标题读不出新结论，因此按导航确认
    节奏重读，读到目标难度即算成功。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        event_type: 活动玩法标识，用于确认调用方选对了 checker。
        mode: 期望的难度。
        attempts: 最大重读次数。
        interval_seconds: 两次重读之间的等待秒数。

    Returns:
        读到目标难度时为真。
    """
    for _ in range(attempts):
        state = read_event_map_state(
            ctx,
            attempts=_PROBE_ATTEMPTS,
            interval_seconds=interval_seconds,
            event_type=event_type,
        )
        if state.current_mode is mode:
            return True
        time.sleep(interval_seconds)
    return False


def check_event_sortie_prepare(
    ctx: ContextHandle,
    *,
    absent: bool = False,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
    event_type: str | None = None,
    stage: str | None = None,
) -> bool:
    """确认节点浮窗是否打开，并在给出章节时校验它指向目标章节。

    参数全部可省略：省略 event_type 时不校验调用方选对了 checker；省略 stage 时只判
    "浮窗已经打开"；absent 为真时只判浮窗消失。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        absent: 期望浮窗消失时为真，默认期望它出现。
        attempts: 识别次数，默认按导航确认节奏。
        interval_seconds: 两次识别之间的等待秒数。
        event_type: 活动玩法标识；提供时校验调用方选对了 checker。
        stage: 目标章节标识，例如 EX7；提供时校验浮窗标题指向该章节。

    Returns:
        断言满足时为真（给出章节时还要标题指向该章节）。

    Raises:
        ValueError: 章节标识格式非法或超出本期范围。
    """
    if event_type is not None:
        _require_activity(event_type)
    # 章节标识同时给出难度和落点序号；格式非法或超出本期范围时在这里就抛错。
    parsed = parse_stage(stage) if stage is not None else None

    # 1. 先判浮窗的出现或消失；断言不满足时不需要继续判定标题。
    if not read_sortie_overlay(
        ctx,
        absent=absent,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ):
        return False

    # 2. 只判浮窗、或浮窗已消失时，到此即算满足。
    if absent or parsed is None:
        return True

    # 3. 再用关卡标题确认进入的是目标章节。
    title_texts = read_stage_title_texts(ctx)
    matched = is_stage_title_matched(
        title_texts,
        node=parsed.node,
        hard=parsed.difficulty is EventMode.HARD,
    )
    _log.debug('[UI] 出征准备前置页 → 校验章节：stage={!r}，matched={!r}', stage, matched)
    return matched


# ── 任务绑定 ────────────────────────────────────────────────────────────────


def read_event_type(ctx: ContextHandle) -> str:
    """读取任务绑定的活动玩法标识。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        活动玩法标识。

    Raises:
        NavigationError: 任务没有绑定活动玩法。
    """
    event_type = ctx.read_event_type()
    if event_type is None:
        raise NavigationError('活动导航需要任务绑定 event_type')
    return event_type


def read_event_stage(ctx: ContextHandle) -> str:
    """读取任务绑定的活动章节标识。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        活动章节标识。

    Raises:
        NavigationError: 任务没有绑定活动章节。
    """
    stage = ctx.read_event_stage()
    if stage is None:
        raise NavigationError('活动导航需要任务绑定 event_stage')
    return stage


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _require_activity(event_type: str) -> None:
    """校验调用方给出的活动玩法标识就是本期活动。

    Args:
        event_type: 调用方给出的活动玩法标识。

    Raises:
        ValueError: 活动玩法标识与本期活动不一致。
    """
    if event_type != ACTIVITY:
        raise ValueError(f'当前 checker 不支持的活动玩法: {event_type!r}')


def _load_template(filename: str) -> Template:
    """加载本活动模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'ACTIVITY',
    'EventMapState',
    'EventMode',
    'EventStage',
    'calculate_current_mode',
    'check_event_entry',
    'check_event_map_page',
    'check_event_sortie_prepare',
    'is_stage_title_matched',
    'parse_stage',
    'read_event_map_state',
    'read_event_stage',
    'read_event_type',
    'read_map_title',
    'read_mode_button',
    'read_mode_button_center',
    'read_sortie_overlay',
    'read_sortie_prepare_center',
    'read_stage_title_texts',
    'wait_event_mode',
]
