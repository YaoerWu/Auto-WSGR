"""模块功能：读取出征页当前能同时看到的页面层。

上层调用：
- application.ui.navigation.registry：作为出征页域的探针，一帧判出当前停在哪个标签页、
  以及上面有没有演习对手浮窗。
- application.ui.navigation.executor：切换标签后确认落点。

下层依赖：
- application.ui.template：加载本模块的激活态模板与浮窗标题模板。
- common.vision：按模板与区域识别当前激活的标签。

边界：只做识别并返回页面结论，不执行点击、不计算路由、不上报识别错误。
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
TEMPLATE_NAMESPACE = 'controller/sortie'

# 五个标签的激活态模板；目录小写、文件名全大写。
# 只保留激活态：标签互斥，一次只有一个激活模板能匹配上。
SORTIE_TAB_TEMPLATE = 'SORTIE_SORTIE_TAB_720P.png'
EXERCISE_TAB_TEMPLATE = 'SORTIE_EXERCISE_TAB_720P.png'
EXPEDITION_TAB_TEMPLATE = 'SORTIE_EXPEDITION_TAB_720P.png'
CAMPAIGN_TAB_TEMPLATE = 'SORTIE_CAMPAIGN_TAB_720P.png'
DECISIVE_TAB_TEMPLATE = 'SORTIE_DECISIVE_TAB_720P.png'

# 演习对手浮窗标题是唯一的浮窗判据：关闭按钮在登录更新弹窗上也能命中 0.95，挑战按钮
# 在无浮窗演习页上能命中 0.78，只有标题模板跨 60+ 张静态图的最高误命中是 0.46。浮窗
# 和标签要在一帧里判层叠关系，所以模板留在本命名空间，不跨 checker 去取。
EXERCISE_OVERLAY_TITLE_TEMPLATE = 'EXERCISE_OVERLAY_TITLE_720P.png'


# ── 识别区域 ────────────────────────────────────────────────────────────────

# 校准基准 1280x720；区域由像素框换算为四位小数，并按 [规范]python-code-style.md
# §6.5 外扩，保证区域大于对应模板。

# 标签栏区域由 SORTIE_TAB_ROI_REPORT.json 的像素框换算。
SORTIE_TAB_ROI = ROI(0.1539, 0.0166, 0.2149, 0.0723)
EXERCISE_TAB_ROI = ROI(0.2796, 0.0152, 0.3438, 0.075)
EXPEDITION_TAB_ROI = ROI(0.4078, 0.0138, 0.4735, 0.0764)
CAMPAIGN_TAB_ROI = ROI(0.5367, 0.0138, 0.6008, 0.0764)
DECISIVE_TAB_ROI = ROI(0.6656, 0.0166, 0.7336, 0.075)

# 浮窗标题区域由 演习页ROI_720P.yaml 的 roi_px 换算。
EXERCISE_OVERLAY_TITLE_ROI = ROI(0.075, 0.2264, 0.2133, 0.2778)

# 页面、模板与识别区域，顺序即由深到浅的返回顺序。
# 浮窗出现时顶部标签栏不被遮挡，浮窗和演习标签会同时命中，所以浮窗排最前。
_LAYERS: tuple[tuple[PageName, str, ROI], ...] = (
    (PageName.EXERCISE_RIVAL_CONFIRM, EXERCISE_OVERLAY_TITLE_TEMPLATE, EXERCISE_OVERLAY_TITLE_ROI),
    (PageName.SORTIE_MAP, SORTIE_TAB_TEMPLATE, SORTIE_TAB_ROI),
    (PageName.EXERCISE, EXERCISE_TAB_TEMPLATE, EXERCISE_TAB_ROI),
    (PageName.EXPEDITION, EXPEDITION_TAB_TEMPLATE, EXPEDITION_TAB_ROI),
    (PageName.CAMPAIGN, CAMPAIGN_TAB_TEMPLATE, CAMPAIGN_TAB_ROI),
    (PageName.DECISIVE_BATTLE, DECISIVE_TAB_TEMPLATE, DECISIVE_TAB_ROI),
)

# 切标签后页面要走一段切换动画；读一帧判层时不需要等，默认只读一次。
_READ_ATTEMPTS = 1
_READ_INTERVAL_SECONDS = 0.5


# ── 当前层 ──────────────────────────────────────────────────────────────────


def read_sortie_layer(
    ctx: ContextHandle,
    *,
    attempts: int = _READ_ATTEMPTS,
    interval_seconds: float = _READ_INTERVAL_SECONDS,
) -> tuple[PageName, ...]:
    """读取出征页当前能同时看到的页面层。

    一次截图比对六个模板：五个标签的激活态加演习对手浮窗标题。标签互斥，
    浮窗与标签可以同时命中，因此按由深到浅返回，第一项就是当前最上层。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 识别次数；判层默认只读一帧，切标签确认时由调用方提高。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        当前能同时看到的页面层，由深到浅；不在出征页体系时为空元组。
    """
    result = expect_template(
        ctx,
        template=tuple(_load_template(filename) for _, filename, _ in _LAYERS),
        roi=tuple(roi for _, _, roi in _LAYERS),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    return tuple(
        page
        for (page, _, _), match in zip(_LAYERS, result.observation, strict=True)
        if match.matched
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(TEMPLATE_NAMESPACE, filename)


__all__ = ['read_sortie_layer']
