"""战役任务定义和入口参数转换。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from autowsgr.application.combat.types import Formation
from autowsgr.application.controller.types import RepairMode, ShipType
from autowsgr.business.combat.fleet import (
    FleetSlotRule,
    ResolvedFleetSelection,
    ShipSelector,
    exact_fleet_rules,
    fleet_presets_from_yaml,
    resolve_fleet_selection,
)
from autowsgr.business.combat.plan import CombatMode, CombatPlan


CAMPAIGN_NAMES: dict[int, str] = {
    1: '驱逐',
    2: '巡洋',
    3: '战列',
    4: '航母',
    5: '潜艇',
}
CAMPAIGN_DAILY_LIMIT = 8

CAMPAIGN_NAME_MAP = {
    f'{label}{name}': (index, difficulty)
    for index, name in CAMPAIGN_NAMES.items()
    for label, difficulty in (('简单', 'easy'), ('困难', 'hard'))
}

CAMPAIGN_FLEET_TYPES: dict[int, tuple[ShipType, ...]] = {
    1: (ShipType.DD,) * 6,
    2: (ShipType.BB, ShipType.CA, ShipType.CA, ShipType.CL, ShipType.CL, ShipType.DD),
    3: (ShipType.BC, ShipType.BB, ShipType.CA, ShipType.CA, ShipType.DD, ShipType.DD),
    4: (ShipType.CV, ShipType.CV, ShipType.DD, ShipType.DD, ShipType.DD, ShipType.DD),
    5: (ShipType.SS,) * 3,
}

CAMPAIGN_FIELDS = frozenset(
    {
        'campaign_name',
        'name',
        'mode',
        'schema_version',
        'chapter',
        'map',
        'fleet',
        'fleet_rules',
        'fleet_presets',
        'formation',
        'night',
        'repair_mode',
        'fight_condition',
        'node_defaults',
        'node_args',
        'selected_nodes',
        'event',
    },
)


def parse_campaign_name(name: str) -> tuple[int, str]:
    """解析 ``简单/困难 + 舰种`` 战役名称。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError('campaign_name 必须是非空字符串')
    result = CAMPAIGN_NAME_MAP.get(name.strip())
    if result is None:
        options = ', '.join(sorted(CAMPAIGN_NAME_MAP))
        raise ValueError(f'无法识别的战役名称: {name!r}，可选: {options}')
    return result


@dataclass(frozen=True, slots=True)
class CampaignSpec:
    """一张已校验的战役任务定义。"""

    campaign_name: str
    map_index: int
    difficulty: str
    plan: CombatPlan
    fleet_selection: ResolvedFleetSelection
    required_ship_types: tuple[ShipType, ...] | None = None
    skip_ship_type_validation: bool = False

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, Any],
    ) -> CampaignSpec:
        """把 API/YAML 参数转换为单次战役计划。"""
        unknown = sorted(set(params) - CAMPAIGN_FIELDS)
        if unknown:
            raise ValueError(f'战役 YAML 包含未知字段: {", ".join(unknown)}')

        campaign_name = params.get('campaign_name')
        map_index, difficulty = parse_campaign_name(campaign_name)
        try:
            _validate_fleet_sources(params)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'战役 YAML 字段校验失败: {exc}') from exc

        data = dict(params)
        data.pop('campaign_name', None)
        data.pop('name', None)

        raw_mode = data.get('mode')
        if raw_mode is not None and raw_mode != CombatMode.BATTLE:
            raise ValueError('战役 YAML 的 mode 必须为 battle')
        data['mode'] = CombatMode.BATTLE
        data.setdefault('repair_mode', RepairMode.moderate_damage.value)

        raw_defaults = data.get('node_defaults')
        defaults = {} if raw_defaults is None else raw_defaults
        if not isinstance(defaults, Mapping):
            raise TypeError('战役字段 node_defaults 必须是对象')
        defaults = dict(defaults)
        if 'formation' in data:
            defaults['formation'] = data.pop('formation')
        if 'night' in data:
            night = data.pop('night')
            if not isinstance(night, bool):
                raise ValueError('战役字段 night 必须是布尔值')
            defaults['night'] = night
        defaults.setdefault('formation', Formation.double_column.value)
        defaults.setdefault('night', True)
        data['node_defaults'] = defaults

        raw_rules = data.pop('fleet_rules', None)
        if raw_rules is not None:
            if data.get('fleet_presets') is not None:
                raise ValueError('战役不能同时提供 fleet_rules 和 fleet_presets')
            if not isinstance(raw_rules, list):
                raise ValueError('战役字段 fleet_rules 必须是列表')
            data['fleet_presets'] = [{'ships': raw_rules}]

        try:
            plan = CombatPlan.from_dict(
                data,
                name=str(params.get('name') or f'战役-{campaign_name}'),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f'战役 YAML 字段校验失败: {exc}') from exc
        selection = resolve_fleet_selection(plan)
        required_ship_types = CAMPAIGN_FLEET_TYPES.get(map_index) if difficulty == 'hard' else None
        skip_ship_type_validation = difficulty == 'hard' and map_index == 1
        if required_ship_types and (
            selection.slot_rules is not None or selection.plain_fleet is not None
        ):
            selection = _apply_hard_campaign_rules(
                selection,
                required_ship_types,
                enforce_types=not skip_ship_type_validation,
            )
        return cls(
            campaign_name=campaign_name.strip(),
            map_index=map_index,
            difficulty=difficulty,
            plan=plan,
            fleet_selection=selection,
            required_ship_types=required_ship_types,
            skip_ship_type_validation=skip_ship_type_validation,
        )


def _validate_fleet_sources(params: Mapping[str, Any]) -> None:
    """拒绝歧义舰队来源，并限制填船槽位数量。"""
    sources = [
        name for name in ('fleet', 'fleet_rules', 'fleet_presets') if params.get(name) is not None
    ]
    if len(sources) > 1:
        raise ValueError('战役只能提供一种舰队来源: fleet、fleet_rules 或 fleet_presets')

    fleet = params.get('fleet')
    if fleet is not None:
        if not isinstance(fleet, list) or not 1 <= len(fleet) <= 6:
            raise ValueError('战役字段 fleet 必须是 1-6 艘舰船名称列表')
        if any(not isinstance(name, str) or not name.strip() for name in fleet):
            raise ValueError('战役字段 fleet 必须是非空字符串列表')
        return

    raw_rules = params.get('fleet_rules')
    if raw_rules is not None:
        if not isinstance(raw_rules, list) or not 1 <= len(raw_rules) <= 6:
            raise ValueError('战役字段 fleet_rules 必须包含 1-6 个槽位')
        fleet_presets_from_yaml([{'ships': raw_rules}])
        return

    raw_presets = params.get('fleet_presets')
    if raw_presets is None:
        return
    if not isinstance(raw_presets, list) or not raw_presets:
        raise ValueError('战役字段 fleet_presets 必须是非空列表')
    presets = fleet_presets_from_yaml(raw_presets)
    assert presets is not None
    if any(len(preset.slots) > 6 for preset in presets):
        raise ValueError('战役舰队 ships 必须包含 1-6 个槽位')


def _apply_hard_campaign_rules(
    selection: ResolvedFleetSelection,
    required_types: tuple[ShipType, ...],
    *,
    enforce_types: bool,
) -> ResolvedFleetSelection:
    """把困难战役的固定舰种约束叠加到用户舰队规则。"""
    rules = selection.slot_rules
    if rules is None:
        assert selection.plain_fleet is not None
        rules = exact_fleet_rules(selection.plain_fleet)
    if len(rules) != len(required_types):
        raise ValueError(
            f'困难战役必须提供 {len(required_types)} 个舰队槽位，当前为 {len(rules)} 个',
        )

    constrained = tuple(
        _restrict_campaign_slot(rule, expected, enforce_types=enforce_types)
        for rule, expected in zip(rules, required_types, strict=True)
    )
    return replace(selection, slot_rules=constrained, plain_fleet=None)


def _restrict_campaign_slot(
    rule: FleetSlotRule,
    expected: ShipType,
    *,
    enforce_types: bool,
) -> FleetSlotRule:
    """校验并固定一个槽位的困难战役舰种。"""
    options = tuple(
        _restrict_campaign_selector(option, expected, enforce_types=enforce_types)
        for option in rule.options
    )
    primary = options[0] if rule.primary is not None else None
    candidates = options[1:] if rule.primary is not None else options
    return FleetSlotRule(primary=primary, candidates=candidates)


def _restrict_campaign_selector(
    selector: ShipSelector,
    expected: ShipType,
    *,
    enforce_types: bool,
) -> ShipSelector:
    if not enforce_types:
        return replace(selector, ship_types=())
    if selector.ship_types and expected not in selector.ship_types:
        raise ValueError(
            f'困难战役槽位要求 {expected.value}，舰船 {selector.name} 的舰种规则不匹配',
        )
    return replace(selector, ship_types=(expected,))
