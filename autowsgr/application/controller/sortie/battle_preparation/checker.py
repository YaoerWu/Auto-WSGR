"""模块功能：识别出征准备页属于哪一种玩法。

上层调用：
- application.ui.navigation：判断当前是不是出征准备页，以及属于哪一种玩法。

下层依赖：
- application.ui.navigation.types：提供页面名。
- application.ui.template：加载本模块模板。
- common.vision：读取模板命中事实。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.ui.navigation.types import PageName
from autowsgr.application.ui.template import load_ui_template
from autowsgr.common.vision import ROI, Template, expect_template


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'navigation/checker/sortie/battle_preparation'

# 四个准备页的模板；目录小写、文件名全大写。
BATTLE_PREPARATION_TEMPLATE = 'BATTLE_PREP_720P.png'
DECISIVE_PREPARATION_TEMPLATE = 'DECISIVE_PREP_720P.png'
EXERCISE_PREPARATION_TEMPLATE = 'EXERCISE_PREP_720P.png'
CAMPAIGN_PREPARATION_TEMPLATE = 'CAMPAIGN_PREP_720P.png'

# 四页共用同一块区域，只在右上角三格快捷按钮（预/装备/奖杯）的占用格数上不同。
# 三格全齐的普通页模板放最后，避免最宽松的模板抢先命中其它页。
_PAGE_TEMPLATES: tuple[tuple[PageName, str], ...] = (
    (PageName.EXERCISE_PREPARATION, EXERCISE_PREPARATION_TEMPLATE),
    (PageName.DECISIVE_BATTLE_PREPARATION, DECISIVE_PREPARATION_TEMPLATE),
    (PageName.CAMPAIGN_PREPARATION, CAMPAIGN_PREPARATION_TEMPLATE),
    (PageName.BATTLE_PREPARATION, BATTLE_PREPARATION_TEMPLATE),
)


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 出征准备页ROI_720P.yaml 的 roi_px=[767, 99, 928, 140] 换算，
# 区域比 160x40 的模板各边大 1px。
BATTLE_PREPARATION_ROI = ROI(0.5993, 0.1375, 0.725, 0.1945)


# ── 进入准备页的等待窗口 ────────────────────────────────────────────────────

_ATTEMPTS = 5
_INTERVAL_SECONDS = 0.5


# ── 当前层 ──────────────────────────────────────────────────────────────────


def read_battle_preparation_layer(
    ctx: ContextHandle,
    *,
    attempts: int = _ATTEMPTS,
    interval_seconds: float = _INTERVAL_SECONDS,
) -> tuple[PageName, ...]:
    """读取当前停在哪一种出征准备页。

    四个准备页共用同一块区域，只有快捷按钮的占用格数不同，因此一次截图就能把四种
    模板全部比对完，不必为每种玩法各截一帧。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足进入准备页的加载动画窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        当前准备页；不是准备页或识别不到时为空元组。
    """
    result = expect_template(
        ctx,
        template=tuple(_load_template(filename) for _, filename in _PAGE_TEMPLATES),
        roi=BATTLE_PREPARATION_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    return tuple(
        page
        for (page, _), match in zip(_PAGE_TEMPLATES, result.observation, strict=True)
        if match.matched
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'BATTLE_PREPARATION_ROI',
    'BATTLE_PREPARATION_TEMPLATE',
    'CAMPAIGN_PREPARATION_TEMPLATE',
    'DECISIVE_PREPARATION_TEMPLATE',
    'EXERCISE_PREPARATION_TEMPLATE',
    'TEMPLATE_NAMESPACE',
    'read_battle_preparation_layer',
]
