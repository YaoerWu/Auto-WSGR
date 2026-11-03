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

from autowsgr.application.controller.sortie.battle_preparation import constants
from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import Template, expect_template


if TYPE_CHECKING:
    from autowsgr.application.navigation.types import PageName
    from autowsgr.dispatch.context import ContextHandle


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
        template=tuple(_load_template(filename) for _, filename in constants.PREPARATION_TEMPLATES),
        roi=constants.BATTLE_PREPARATION_ROI,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    return tuple(
        page
        for (page, _), match in zip(
            constants.PREPARATION_TEMPLATES, result.observation, strict=True
        )
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
        template=tuple(_load_template(filename) for filename in constants.TEAM_TAB_TEMPLATES),
        roi=constants.TEAM_TAB_ROIS,
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
    return load_ui_template(constants.TEMPLATE_NAMESPACE, filename)


__all__ = [
    'read_battle_preparation_layer',
    'read_team_tab',
]
