"""模块功能：定义编队选择规则和解析后的舰队选择值对象。

上层调用：
- business.combat：提供编队配置和已解析的舰队选择规则。
- application.ui.controller.fleet：消费槽位规则执行编队识别和调整。

下层依赖：
- common.types：提供舰种类型。

本模块只保存无设备依赖的编队规则和数据契约，不执行页面操作或 OCR。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Sequence

    from autowsgr.application.controller.types import ShipType


@dataclass(frozen=True, slots=True)
class ShipSelector:
    """A primary or fallback ship selection rule."""

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
    """A primary selector and ordered fallback selectors for one slot."""

    primary: ShipSelector | None = None
    candidates: tuple[ShipSelector, ...] = ()

    def __post_init__(self) -> None:
        if self.primary is None and not self.candidates:
            raise ValueError('位置至少需要一艘主选或备选舰船')

    @property
    def options(self) -> tuple[ShipSelector, ...]:
        """Return all selectors in selection order."""
        if self.primary is None:
            return self.candidates
        return (self.primary, *self.candidates)

    @property
    def preferred_name(self) -> str:
        """Return the first selector name."""
        return self.options[0].name


@dataclass(frozen=True, slots=True)
class FleetPreset:
    """A parsed fleet preset."""

    name: str
    slots: tuple[FleetSlotRule, ...]


class FleetSelectionSource(StrEnum):
    """Source of a resolved fleet selection."""

    OVERRIDE_RULES = 'override_rules'
    OVERRIDE_FLEET = 'override_fleet'
    PLAN_PRESET = 'plan_preset'
    PLAN_FLEET = 'plan_fleet'
    NONE = 'none'


@dataclass(frozen=True, slots=True)
class ResolvedFleetSelection:
    """The single fleet selection passed to an executor."""

    fleet_id: int
    slot_rules: tuple[FleetSlotRule, ...] | None
    plain_fleet: tuple[str, ...] | None
    source: FleetSelectionSource

    @property
    def primary_names(self) -> list[str | None] | None:
        """Return primary names for combat result metadata."""
        if self.slot_rules is not None:
            return [
                rule.primary.name if rule.primary is not None else None
                for rule in self.slot_rules[:6]
            ]
        return list(self.plain_fleet) if self.plain_fleet is not None else None


def exact_fleet_rules(names: Sequence[str]) -> tuple[FleetSlotRule, ...]:
    """Convert plain ship names into exact slot rules."""
    return tuple(FleetSlotRule(primary=ShipSelector(name=name)) for name in names)


__all__ = [
    'FleetPreset',
    'FleetSelectionSource',
    'FleetSlotRule',
    'ResolvedFleetSelection',
    'ShipSelector',
    'exact_fleet_rules',
]
