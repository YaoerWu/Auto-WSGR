"""食堂做菜操作。

导航到食堂页面并委托 UI 层执行做菜。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.controller.backyard.canteen import CanteenPage
from autowsgr.application.navigation import goto_page
from autowsgr.common.system.logger import get_logger
from autowsgr.common.types import PageName


if TYPE_CHECKING:
    from autowsgr.application.runtime import RuntimeContext as GameContext

_log = get_logger('ops')


def cook(
    ctx: GameContext,
    *,
    position: int = 1,
    force_cook: bool = False,
) -> bool:
    """在食堂做菜。

    Parameters
    ----------
    position:
        菜谱编号 (1-3)。
    force_cook:
        当有菜正在生效时是否继续做菜。
    """
    _log.info('[OPS] 做菜开始')
    goto_page(ctx, PageName.CANTEEN)
    page = CanteenPage(ctx)
    result = page.cook(position, force_cook=force_cook)
    _log.info('[OPS] 做菜完成')
    return result
