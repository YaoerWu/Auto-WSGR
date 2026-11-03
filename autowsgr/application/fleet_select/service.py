"""模块功能：换船模块唯一对外入口，按换船模式分发到具体编排。

上层调用：
- business：出征、活动、演习、决战、战役任务在准备舰队时调用 adjust_fleet。

下层依赖：
- fleet_select.models.normal：普通出征、活动、演习的换船编排。
- fleet_select.models.decisive：决战准备页的换船编排。
- fleet_select.models.campaign：战役准备页的换船编排。

边界：只做模式校验与分发，不含换船步骤。三套编排各有各的页面能力：普通出征与
活动、演习有队伍页签和搜索框；决战没有搜索框但可以拖拽；战役既没有队伍页签也没有
拖拽，只能一槽一船替换。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autowsgr.application.fleet_select.models import campaign, decisive, normal
from autowsgr.application.fleet_select.rules.shipnames import apply_ship_name_aliases
from autowsgr.application.fleet_select.types import FleetSelectMode


if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from autowsgr.application.fleet_select.types import FleetSlotRule, FleetSnapshot
    from autowsgr.dispatch.context import ContextHandle


def adjust_fleet(
    ctx: ContextHandle,
    *,
    mode: FleetSelectMode,
    fleet_rules: Sequence[FleetSlotRule | str | None],
    fleet_id: int | None = None,
    reset_fleet: bool = True,
    ship_name_map: Mapping[str, str] | None = None,
    notify: Callable[[str, dict[str, object]], None] | None = None,
) -> FleetSnapshot | None:
    """按换船模式把准备页舰队调整成目标编成。

    Args:
        ctx: 提供设备服务与截图事实的 dispatch 上下文句柄。
        mode: 换船模式，决定走哪一套编排。
        fleet_rules: 逐槽规则，可以只写舰名；不足六槽的按空槽补齐。
        fleet_id: 目标舰队编号 1-4；只有普通出征、活动与演习支持切换队伍。
        reset_fleet: 战役模式调整前是否先清空全部物理槽位。
        ship_name_map: 系统标准船名到游戏内显示船名的映射，为空时按标准名搜索。
        notify: 换船过程中每完成一个动作时的上报回调。

    Returns:
        调整完成后的舰队快照；目标编成无解或主选最终无法确认时返回 None，
        由上层决定降级跳过还是换一套编成。

    Raises:
        ValueError: 决战或战役模式被要求切换队伍。
    """
    aliases = {
        display_name: system_name for system_name, display_name in (ship_name_map or {}).items()
    }
    with apply_ship_name_aliases(aliases):
        if mode is FleetSelectMode.NORMAL:
            return normal.adjust_normal_fleet(
                ctx,
                fleet_rules=fleet_rules,
                fleet_id=fleet_id,
                notify=notify,
            )

        if fleet_id is not None:
            raise ValueError(f'换船模式 {mode.value!r} 没有队伍页签，不能指定舰队编号 {fleet_id}')

        if mode is FleetSelectMode.DECISIVE:
            return decisive.adjust_decisive_fleet(ctx, fleet_rules=fleet_rules, notify=notify)

        return campaign.adjust_campaign_fleet(
            ctx,
            fleet_rules=fleet_rules,
            reset_fleet=reset_fleet,
            notify=notify,
        )


__all__ = ['adjust_fleet']
