"""模块功能：识别出征准备页属于哪一种玩法，并读取当前舰队编号。

上层调用：
- application.navigation：判断当前是不是出征准备页，以及属于哪一种玩法。
- application.fleet_select.operation.team_select：读取切换舰队前后的当前队编号。

下层依赖：
- application.navigation.types：提供页面名。
- application.controller.template：加载本模块模板。
- common.vision：读取模板命中事实。

边界：只做识别并返回结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.template import load_ui_template
from autowsgr.application.navigation.types import PageName
from autowsgr.common.vision import ROI, Template, expect_template


if TYPE_CHECKING:
    from autowsgr.dispatch.context import ContextHandle


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation'

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

# 四个舰队的选中态模板；只有被选中的那一队是亮蓝高亮块，其余三队为暗色。
TEAM_TAB_TEMPLATES: tuple[str, ...] = (
    'TEAM_1_ACTIVE_720P.png',
    'TEAM_2_ACTIVE_720P.png',
    'TEAM_3_ACTIVE_720P.png',
    'TEAM_4_ACTIVE_720P.png',
)


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；由 出征准备页ROI_720P.yaml 的 roi_px=[767, 99, 928, 140] 换算，
# 区域比 160x40 的模板各边大 1px。
BATTLE_PREPARATION_ROI = ROI(0.5993, 0.1375, 0.725, 0.1945)

# 四个舰队标签页的搜索区，与 TEAM_TAB_TEMPLATES 一一对应，由
# 出征准备页状态ROI_720P.yaml 的 roi_normalized 抄录。
# 四队底色相同、只差队列数字，共享区域会互相误命中（交叉分 0.87 以上），
# 因此每队配一块只容 ±1px 滑动的窄区域；实测交叉分降到 0.72 以下。
TEAM_TAB_ROIS: tuple[ROI, ...] = (
    ROI(0.08125, 0.12777778, 0.1421875, 0.19722222),
    ROI(0.20859375, 0.13055556, 0.26171875, 0.19444444),
    ROI(0.33046875, 0.12916667, 0.38671875, 0.19444444),
    ROI(0.4546875, 0.12777778, 0.5109375, 0.19722222),
)


# ── 页面响应窗口 ────────────────────────────────────────────────────────────

# 进入准备页与切换舰队都要等页面重绘：重试 5 次、间隔 0.5 秒，覆盖转场动画与卡片刷新。
_PAGE_RESPONSE_ATTEMPTS = 5
_PAGE_RESPONSE_INTERVAL_SECONDS = 0.5


# ── 当前层 ──────────────────────────────────────────────────────────────────


def read_battle_preparation_layer(
    ctx: ContextHandle,
    *,
    attempts: int = _PAGE_RESPONSE_ATTEMPTS,
    interval_seconds: float = _PAGE_RESPONSE_INTERVAL_SECONDS,
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


# ── 当前舰队的编号 ──────────────────────────────────────────────────────────


def read_team_tab(
    ctx: ContextHandle,
    *,
    attempts: int = _PAGE_RESPONSE_ATTEMPTS,
    interval_seconds: float = _PAGE_RESPONSE_INTERVAL_SECONDS,
) -> int | None:
    """读取当前选中的舰队编号。

    四队共用同一排标签页，只有选中的那一队亮起，因此每队模板配一块窄区域后，一次截图
    就能把四队全部比对完，不必为每队各截一帧。相邻两队底色相近，画质波动时可能同时越过
    阈值，此时取分数最高的一队，避免按模板顺序取到错的相邻队。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数，默认给足切换舰队后的响应窗口。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        选中的舰队编号 1 到 4；没有选中任何一队或识别不到时为空。
    """
    result = expect_template(
        ctx,
        template=tuple(_load_template(filename) for filename in TEAM_TAB_TEMPLATES),
        roi=TEAM_TAB_ROIS,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    best_team: int | None = None
    best_score = 0.0
    for team, match in enumerate(result.observation, start=1):
        if match.matched and match.score > best_score:
            best_team, best_score = team, match.score
    return best_team


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = [
    'read_battle_preparation_layer',
    'read_team_tab',
]
