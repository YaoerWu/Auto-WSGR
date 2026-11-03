"""模块功能：读取出征页当前能同时看到的页面层。

上层调用：
- application.navigation.registry：作为出征页域的探针，一帧判出当前停在哪个标签页、
  以及上面有没有演习对手浮窗。
- application.navigation.executor：切换标签后确认落点。

下层依赖：
- application.controller.template：加载本模块的激活态模板与浮窗标题模板。
- common.vision：按模板与区域识别当前激活的标签。

边界：只做识别并返回页面结论，不执行点击、不计算路由、不上报识别错误。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie import constants
from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.vision import Template, expect_template


if TYPE_CHECKING:
    from autowsgr.application.navigation.types import PageName
    from autowsgr.dispatch.context import ContextHandle


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
        template=tuple(_load_template(filename) for _, filename, _ in constants.SORTIE_LAYERS),
        roi=tuple(roi for _, _, roi in constants.SORTIE_LAYERS),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    return tuple(
        page
        for (page, _, _), match in zip(constants.SORTIE_LAYERS, result.observation, strict=True)
        if match.matched
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _load_template(filename: str) -> Template:
    """加载本模块模板。"""
    return load_ui_template(constants.TEMPLATE_NAMESPACE, filename)


__all__ = ['read_sortie_layer']
