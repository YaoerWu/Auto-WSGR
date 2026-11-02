"""模块功能：定义换船规则与舰队事实的数据模型。

上层调用：
- application.fleet_select：规则归一化、槽位分配、换船编排共用这些模型。
- business：向下引用换船规则，不再自己维护一份。

下层依赖：
- application.controller.types：舰种枚举。

边界：只保存数据契约与构造参数校验，不读页面、不点击、不编排流程。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.common.system.enums import StrEnum


if TYPE_CHECKING:
    from autowsgr.application.controller.types import ShipType


# ── 编队规模 ────────────────────────────────────────────────────────────────

FLEET_SLOT_COUNT = 6  # 编队槽位数，换船规则的合法长度。


# ── 换船模式 ────────────────────────────────────────────────────────────────


class FleetSelectMode(StrEnum):
    """换船模式，决定走哪一套编排，也决定哪些能力可用。"""

    NORMAL = 'normal'  # 普通出征 / 活动 / 演习：全局规划 + 拖拽调序
    DECISIVE = 'decisive'  # 决战：一萝卜一坑 + 可拖拽
    CAMPAIGN = 'campaign'  # 战役：一萝卜一坑 + 不可拖拽


# ── 规则模型 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ShipSelector:
    """一条主选或备选的选船规则。"""

    name: str
    search_name: str | None = None
    ship_types: tuple[ShipType, ...] = ()
    min_level: int | None = None
    max_level: int | None = None
    relaxed_constraints: bool = False

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError('name 不能为空')
        object.__setattr__(self, 'name', name)

        search_name = self.search_name.strip() if self.search_name else None
        object.__setattr__(self, 'search_name', search_name)
        if self.min_level is not None and self.min_level < 1:
            raise ValueError('min_level 必须大于等于 1')
        if self.max_level is not None and self.max_level < 1:
            raise ValueError('max_level 必须大于等于 1')
        if (
            self.min_level is not None
            and self.max_level is not None
            and self.max_level < self.min_level
        ):
            raise ValueError('max_level 必须大于或等于 min_level')


@dataclass(frozen=True, slots=True)
class FleetSlotRule:
    """一个槽位的主选规则与有序备选规则。"""

    primary: ShipSelector | None = None
    candidates: tuple[ShipSelector, ...] = ()

    def __post_init__(self) -> None:
        if self.primary is None and not self.candidates:
            raise ValueError('位置至少需要一艘主选或备选舰船')

    @property
    def options(self) -> tuple[ShipSelector, ...]:
        """按选择顺序返回该槽位的全部规则。"""
        if self.primary is None:
            return self.candidates
        return (self.primary, *self.candidates)

    @property
    def preferred_name(self) -> str:
        """返回该槽位第一个规则的舰名。"""
        return self.options[0].name


@dataclass(frozen=True, slots=True)
class FleetPreset:
    """一份解析后的编队预设。"""

    name: str
    slots: tuple[FleetSlotRule, ...]


# ── 舰队事实 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FleetSnapshot:
    """一次或多次截图合并得到的六个槽位事实。"""

    names: tuple[str | None, ...]
    occupied: tuple[bool, ...]
    ship_types: tuple[ShipType | None, ...] | None = None
    ship_levels: tuple[int | None, ...] | None = None

    @property
    def unknown_slots(self) -> list[int]:
        """返回已占用但尚未识别舰名的槽位。"""
        return [
            slot
            for slot, (name, occupied) in enumerate(zip(self.names, self.occupied, strict=True))
            if name is None and occupied
        ]

    @property
    def unknown_type_slots(self) -> list[int]:
        """返回已占用但尚未识别舰种的槽位。"""
        ship_types = self.ship_types or (None,) * len(self.occupied)
        return [
            slot
            for slot, (ship_type, occupied) in enumerate(
                zip(ship_types, self.occupied, strict=True),
            )
            if ship_type is None and occupied
        ]

    @property
    def unknown_level_slots(self) -> list[int]:
        """返回已占用但尚未识别等级的槽位。"""
        ship_levels = self.ship_levels or (None,) * len(self.occupied)
        return [
            slot
            for slot, (level, occupied) in enumerate(zip(ship_levels, self.occupied, strict=True))
            if level is None and occupied
        ]

    @property
    def has_unknown_details(self) -> bool:
        """返回是否仍有需要定点补识别的槽位字段。"""
        return bool(self.unknown_slots or self.unknown_type_slots or self.unknown_level_slots)


__all__ = [
    'FLEET_SLOT_COUNT',
    'FleetPreset',
    'FleetSelectMode',
    'FleetSlotRule',
    'FleetSnapshot',
    'ShipSelector',
]
