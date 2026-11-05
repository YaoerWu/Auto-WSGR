"""舰队规则领域模型和入口转换。

YAML 与 HTTP 请求只在各自入口转换一次。执行器和 UI 只接收本模块定义的
不可变对象，不再解释字典、Pydantic DTO 或旧 candidates 字符串格式。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.types import ShipType
from autowsgr.business.fleet_policy import FLEET_POLICIES, FleetPolicy
from autowsgr.common.fleet import (
    FleetPreset,
    FleetSelectionSource,
    FleetSlotRule,
    ResolvedFleetSelection,
    ShipSelector,
    exact_fleet_rules,
)
from autowsgr.common.fleet_types import (
    FLEET_VESSEL_TYPE_BY_CODE,
    FLEET_VESSEL_TYPES,
)


if TYPE_CHECKING:
    from autowsgr_native.vessel_type import VesselType

    from autowsgr.business.combat.plan import CombatPlan


_NATIVE_CODE_TO_SHIP_TYPE: Mapping[str, ShipType] = MappingProxyType(
    {
        'cv': ShipType.CV,
        'cvl': ShipType.CVL,
        'av': ShipType.AV,
        'bb': ShipType.BB,
        'bbv': ShipType.BBV,
        'bc': ShipType.BC,
        'ca': ShipType.CA,
        'cav': ShipType.CAV,
        'clt': ShipType.CLT,
        'cl': ShipType.CL,
        'bm': ShipType.BM,
        'dd': ShipType.DD,
        'ssg': ShipType.SSG,
        'ss': ShipType.SS,
        'sc': ShipType.SC,
        'ap': ShipType.NAP,
        'asdg': ShipType.ASDG,
        'aadg': ShipType.AADG,
        'kp': ShipType.KP,
        'cg': ShipType.CG,
        'bbg': ShipType.BG,
        'bg': ShipType.CBG,
    },
)
"""native 0.3 舰种代码到 AutoWSGR 领域枚举的显式映射。"""

VESSEL_TYPE_TO_SHIP_TYPE: tuple[tuple[VesselType, ShipType], ...] = tuple(
    (vessel_type.native, _NATIVE_CODE_TO_SHIP_TYPE[vessel_type.code])
    for vessel_type in FLEET_VESSEL_TYPES
)

for _native_type, _ship_type in VESSEL_TYPE_TO_SHIP_TYPE:
    if _native_type.as_chinese() != _ship_type.value:
        raise RuntimeError(
            f'native 舰种中文语义不一致: {_native_type.as_english()}',
        )


def ship_type_from_native(vessel_type: VesselType) -> ShipType:
    """把 native 普通舰种转换为 AutoWSGR 领域枚举。"""
    for native_type, ship_type in VESSEL_TYPE_TO_SHIP_TYPE:
        if vessel_type == native_type:
            return ship_type
    message = f'不支持的 native 舰种: {vessel_type!r}'
    raise ValueError(message)


NATIVE_VESSEL_TYPE_BY_CODE: Mapping[str, VesselType] = MappingProxyType(
    {code: vessel_type.native for code, vessel_type in FLEET_VESSEL_TYPE_BY_CODE.items()},
)
"""API 使用的 native 0.3 canonical 舰种代码。"""


SHIP_TYPE_BY_CODE: Mapping[str, tuple[ShipType, ...]] = MappingProxyType(
    {
        **{
            code: (ship_type_from_native(vessel_type),)
            for code, vessel_type in NATIVE_VESSEL_TYPE_BY_CODE.items()
        },
        'ss_or_ssg': (ShipType.SS, ShipType.SSG),
    },
)
"""API 舰种代码到后端领域枚举的唯一映射。"""

_SHIP_TYPE_LABEL_TO_CODE: Mapping[str, str] = MappingProxyType(
    {
        ship_types[0].value: code
        for code, ship_types in SHIP_TYPE_BY_CODE.items()
        if code != 'ss_or_ssg' and len(ship_types) == 1
    },
)

LEGACY_SHIP_TYPE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        'cf': 'cv',
        'cgaa': 'cg',
        'cbg': 'bg',
        'ddg': 'asdg',
        'ddgaa': 'aadg',
    },
)
"""旧版 API/GUI 舰种代码到 canonical code 的兼容映射。"""

_ALL_SHIP_TYPE_CODES = {
    *SHIP_TYPE_BY_CODE,
    *LEGACY_SHIP_TYPE_ALIASES,
}

ALLOWED_SHIP_TYPE_CODES = frozenset(_ALL_SHIP_TYPE_CODES)


def parse_ship_type_codes(raw: object) -> tuple[ShipType, ...]:
    """校验舰种缩写并转换为去重后的领域枚举。"""
    if raw is None or raw == '':
        return ()
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, Sequence):
        raise TypeError('ship_type 必须是非空字符串列表')

    result: list[ShipType] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('ship_type 必须是非空字符串列表')
        text = value.strip()
        code = _SHIP_TYPE_LABEL_TO_CODE.get(text, text.lower())
        canonical_code = LEGACY_SHIP_TYPE_ALIASES.get(code, code)
        ship_types = SHIP_TYPE_BY_CODE.get(canonical_code)
        if ship_types is None:
            allowed = ', '.join(sorted(ALLOWED_SHIP_TYPE_CODES))
            raise ValueError(f'ship_type 不合法: {value!r}, 可选值: {allowed}')
        for ship_type in ship_types:
            if ship_type not in result:
                result.append(ship_type)
    return tuple(result)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError('舰船名称必须是字符串')
    return value.strip() or None


def _optional_level(rule: Mapping[str, Any], field: str) -> int | None:
    value = rule.get(field)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f'{field} 必须是整数')
    return value


def _optional_relaxed(rule: Mapping[str, Any]) -> bool:
    """读取宽松校验开关；缺省为 False（严格校验）。"""
    value = rule.get('relaxed')
    if value is None and 'strict' in rule:
        strict = rule['strict']
        if not isinstance(strict, bool):
            raise TypeError('strict 必须是布尔值')
        return not strict
    if value is None:
        return False
    if not isinstance(value, bool):
        raise TypeError('relaxed 必须是布尔值')
    return value


def _selector_from_mapping(
    raw: Mapping[str, Any],
    *,
    inherited: Mapping[str, Any] | None = None,
) -> ShipSelector:
    name = _optional_text(raw.get('name'))
    if name is None:
        raise ValueError('name 不能为空')
    source = raw if inherited is None else inherited
    inherited_search_name = inherited.get('search_name') if inherited is not None else None
    return ShipSelector(
        name=name,
        search_name=_optional_text(raw.get('search_name', inherited_search_name)),
        ship_types=parse_ship_type_codes(source.get('ship_type', source.get('type'))),
        min_level=_optional_level(source, 'min_level'),
        max_level=_optional_level(source, 'max_level'),
        relaxed_constraints=_optional_relaxed(raw),
    )


def _deduplicate_selectors(selectors: Sequence[ShipSelector]) -> tuple[ShipSelector, ...]:
    """按完整规则去重，保留同名但约束不同的有序候选。"""
    result: list[ShipSelector] = []
    for selector in selectors:
        if selector not in result:
            result.append(selector)
    return tuple(result)


def fleet_slot_from_api(raw: str | Mapping[str, Any]) -> FleetSlotRule:
    """把已经通过 HTTP schema 的槽位转换成 canonical 规则。"""
    if isinstance(raw, str):
        return FleetSlotRule(primary=ShipSelector(name=raw))
    if not isinstance(raw, Mapping):
        raise TypeError('舰队槽位必须是字符串或规则对象')

    name = _optional_text(raw.get('name'))
    primary = _selector_from_mapping(raw) if name is not None else None
    raw_candidates = raw.get('candidates', raw.get('alternatives', []))
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, str):
        raise TypeError('candidates 必须是规则对象列表')
    candidates = _deduplicate_selectors(
        tuple(
            ShipSelector(
                name=candidate,
                search_name=_optional_text(raw.get('search_name')),
                ship_types=parse_ship_type_codes(raw.get('ship_type', raw.get('type'))),
                min_level=_optional_level(raw, 'min_level'),
                max_level=_optional_level(raw, 'max_level'),
            )
            if isinstance(candidate, str)
            else _selector_from_mapping(candidate)
            for candidate in raw_candidates
        )
    )
    return FleetSlotRule(primary=primary, candidates=candidates)


def fleet_slot_from_yaml(raw: object) -> FleetSlotRule:
    """把 YAML 槽位转换成 canonical 规则，并仅在此兼容旧字符串候选。"""
    if isinstance(raw, str):
        return FleetSlotRule(primary=ShipSelector(name=raw))
    if not isinstance(raw, Mapping):
        raise TypeError('舰队槽位必须是字符串或规则对象')

    raw_candidates = raw.get('candidates', raw.get('alternatives', []))
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, str):
        raise TypeError('candidates 必须是列表')
    candidates = list(raw_candidates)

    primary: ShipSelector | None = None
    if _optional_text(raw.get('name')) is not None:
        primary = _selector_from_mapping(raw)
    normalized_candidates: list[ShipSelector] = []
    for candidate in candidates:
        if isinstance(candidate, str):
            selector = _selector_from_mapping(
                {'name': candidate},
                inherited=raw,
            )
        elif isinstance(candidate, Mapping):
            selector = _selector_from_mapping(candidate)
        else:
            raise TypeError('candidates 只能包含舰名字符串或规则对象')
        normalized_candidates.append(selector)
    return FleetSlotRule(
        primary=primary,
        candidates=_deduplicate_selectors(normalized_candidates),
    )


def fleet_presets_from_yaml(raw: object) -> tuple[FleetPreset, ...] | None:
    """解析 YAML 的舰队预设列表。"""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise TypeError('fleet_presets 必须是列表')

    presets: list[FleetPreset] = []
    for raw_preset in raw:
        if not isinstance(raw_preset, Mapping):
            raise TypeError('fleet_presets 每一项必须是对象')
        name = _optional_text(raw_preset.get('name')) or ''
        raw_slots = raw_preset.get('ships')
        if not isinstance(raw_slots, list):
            raise TypeError('fleet_presets.ships 必须是非空列表')
        if not raw_slots:
            raise ValueError('fleet_presets 不能包含空 ships')
        presets.append(
            FleetPreset(
                name=name,
                slots=tuple(fleet_slot_from_yaml(slot) for slot in raw_slots),
            ),
        )
    return tuple(presets)


def resolve_fleet_selection(
    plan: CombatPlan,
    *,
    fleet_id: int | None = None,
    fleet: Sequence[str] | None = None,
    slot_rules: Sequence[FleetSlotRule] | None = None,
) -> ResolvedFleetSelection:
    """按 override rules > override fleet > plan preset > plan fleet 集中解析。"""
    if fleet is not None and len(fleet) == 0:
        raise ValueError('fleet 不能为空')
    if slot_rules is not None and len(slot_rules) == 0:
        raise ValueError('fleet_rules 不能为空')
    resolved_id = fleet_id if fleet_id is not None else plan.fleet_id
    if slot_rules is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=tuple(slot_rules),
            plain_fleet=None,
            source=FleetSelectionSource.OVERRIDE_RULES,
        )
    if fleet is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=None,
            plain_fleet=tuple(fleet),
            source=FleetSelectionSource.OVERRIDE_FLEET,
        )
    plan_presets = plan.fleet_presets
    if isinstance(plan_presets, list):
        plan_presets = fleet_presets_from_yaml(plan_presets)
    if plan_presets:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=plan_presets[0].slots,
            plain_fleet=None,
            source=FleetSelectionSource.PLAN_PRESET,
        )
    if plan.fleet is not None:
        return ResolvedFleetSelection(
            fleet_id=resolved_id,
            slot_rules=None,
            plain_fleet=tuple(plan.fleet),
            source=FleetSelectionSource.PLAN_FLEET,
        )
    return ResolvedFleetSelection(
        fleet_id=resolved_id,
        slot_rules=None,
        plain_fleet=None,
        source=FleetSelectionSource.NONE,
    )


def validate_fleet_selection_arguments(
    fleet_selection: ResolvedFleetSelection | None,
    *,
    fleet_id: int | None,
    fleet: Sequence[str] | None,
    slot_rules: Sequence[FleetSlotRule] | None,
) -> None:
    """拒绝同时提供 canonical selection 和旧式舰队 override。"""
    if fleet_selection is not None and any(
        value is not None for value in (fleet_id, fleet, slot_rules)
    ):
        raise ValueError('fleet_selection 不能同时传入 fleet_id、fleet 或 fleet_rules')


__all__ = [
    'ALLOWED_SHIP_TYPE_CODES',
    'FLEET_POLICIES',
    'NATIVE_VESSEL_TYPE_BY_CODE',
    'FleetPolicy',
    'FleetPreset',
    'FleetSelectionSource',
    'FleetSlotRule',
    'ResolvedFleetSelection',
    'ShipSelector',
    'exact_fleet_rules',
    'fleet_presets_from_yaml',
    'fleet_slot_from_api',
    'fleet_slot_from_yaml',
    'resolve_fleet_selection',
    'ship_type_from_native',
    'validate_fleet_selection_arguments',
]
