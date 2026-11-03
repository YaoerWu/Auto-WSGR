"""模块功能：识别出征准备页的快速整备状态。

上层调用：
- 暂无生产调用方：整备流程接线（任务书 P4）后由应用层判断自动补给是否开启、
  快速修理页签是否激活，并取点击落点。

下层依赖：
- application.controller.template：加载本模块模板。
- common.vision：读取模板匹配事实与命中中心。

边界：只做识别并返回结论，不执行点击、不判断业务是否需要整备、不上报识别错误。
血条状态属于舰队事实，由 ship_recognition.checker 统一读取，本模块不再重复识别。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.template import load_ui_template
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


_log = get_logger('controller.sortie.battle_preparation.quick_maintenance.checker')


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 本模块在 UI 模板根下的命名空间。
TEMPLATE_NAMESPACE = 'controller/sortie/battle_preparation/quick_maintenance'

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

# 快速修理页签像素范围 [469, 538, 651, 590]；限定在页签附近搜索，
# 防止 179x49 的模板滑到右侧「快速补给」页签上。
QUICK_REPAIR_ROI = ROI(0.3664, 0.7472, 0.5086, 0.8194)

# 「全部修理」按钮像素范围 [1022, 464, 1174, 518]，比 151x53 的模板各边大 1px。
ALL_REPAIR_BUTTON_ROI = ROI(0.7984375, 0.64444444, 0.9171875, 0.71944444)

# 修理道具存量文字像素范围 [1136, 398, 1204, 432]；左边界贴着数字前的斜杠右侧，
# 再往左会把斜杠读成数字 1。
REPAIR_STOCK_ROI = ROI(0.8875, 0.55277778, 0.940625, 0.6)


# ── 页面响应窗口 ────────────────────────────────────────────────────────────

# 页签和「全部修理」按钮要一起命中才算进了修理视图；面板联动有延迟，
# 给四帧、每帧间隔 0.5 秒。
_QUICK_REPAIR_ATTEMPTS = 4
_QUICK_REPAIR_INTERVAL_SECONDS = 0.5


# ── 页面状态 ────────────────────────────────────────────────────────────────


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
    """判断快速修理视图是否已激活。

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
    _log.debug(
        '[UI] 识别 → 未读到工具存量：texts={!r}',
        [detection.recognized_text for detection in result.observation],
    )
    return None


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
    'check_auto_supply_enabled',
    'check_quick_repair_active',
    'read_all_repair_center',
    'read_auto_supply_center',
    'read_quick_repair_center',
    'read_repair_tool_count',
]
