"""模块功能：敌方编成与阵型的规则评估。

规则来自作战计划的 enemy_rules / enemy_formation_rules 字段，旧格式形如
[["(BB >= 2) and (CV > 0)", "retreat"], ["单纵阵", 4]]。这里把条件字符串解析
成结构化比较，替代旧代码的 eval()。

上层调用：
- application.combat.engine.decision：索敌成功后按规则决定撤退、迂回或战斗。
- business.combat.plan：从 YAML 配置构建规则引擎。

边界：只把「敌方编成是什么」翻译成「该做什么」；不点按钮、不认画面。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from autowsgr.application.combat.types import Formation
from autowsgr.business.combat.fleet_types import FLEET_VESSEL_TYPES
from autowsgr.common.system.logger import get_logger


_log = get_logger('combat')

_RULE_FIELD_CODES = {vessel_type.native.as_english() for vessel_type in FLEET_VESSEL_TYPES} | {
    'ALL',
}
"""允许出现在规则里的舰种代码。"""

_LEGACY_RULE_FIELD_ALIASES = {'NAP': 'AP', 'CBG': 'BG'}
"""旧配置里沿用的舰种别名。"""


class RuleResult(Enum):
    """规则评估结果。"""

    NO_ACTION = auto()
    """无特殊动作，正常进入战斗。"""

    RETREAT = auto()
    """撤退。"""

    DETOUR = auto()
    """迂回。"""

    FORMATION = auto()
    """选择指定阵型（附带 formation 值）。"""


@dataclass(frozen=True, slots=True)
class RuleAction:
    """规则评估出的具体动作。

    Attributes:
        result: 动作类型。
        formation: result 为 FORMATION 时指定的阵型。
    """

    result: RuleResult
    formation: Formation | None = None

    @staticmethod
    def no_action() -> RuleAction:
        """不采取特殊动作。"""
        return RuleAction(result=RuleResult.NO_ACTION)

    @staticmethod
    def retreat() -> RuleAction:
        """撤退。"""
        return RuleAction(result=RuleResult.RETREAT)

    @staticmethod
    def detour() -> RuleAction:
        """迂回。"""
        return RuleAction(result=RuleResult.DETOUR)

    @staticmethod
    def set_formation(formation: Formation) -> RuleAction:
        """指定阵型。"""
        return RuleAction(result=RuleResult.FORMATION, formation=formation)


_OPERATORS: dict[str, Any] = {
    '>': lambda a, b: a > b,
    '>=': lambda a, b: a >= b,
    '<': lambda a, b: a < b,
    '<=': lambda a, b: a <= b,
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
}


@dataclass(frozen=True, slots=True)
class Condition:
    """单个比较条件。

    Attributes:
        field: 要检查的字段名（如 BB、CV、total），支持 a+b 求和。
        op: 比较操作符。
        value: 比较目标值。
    """

    field: str
    op: str
    value: int | float

    def __post_init__(self) -> None:
        """校验操作符。"""
        if self.op not in _OPERATORS:
            raise ValueError(f"不支持的操作符: '{self.op}'，支持: {list(_OPERATORS)}")

    def evaluate(self, context: dict[str, int | float]) -> bool:
        """在给定编成上下文里评估此条件。"""
        if '+' in self.field:
            parts = [part.strip() for part in self.field.split('+')]
            actual = sum(context.get(part, 0) for part in parts)
        else:
            actual = context.get(self.field, 0)
        return _OPERATORS[self.op](actual, self.value)


@dataclass(frozen=True, slots=True)
class Rule:
    """一条规则：所有条件都满足时触发指定动作。

    Attributes:
        conditions: 需要全部满足的条件（AND 语义）。
        action: 条件全部满足时返回的动作。
    """

    conditions: list[Condition]
    action: RuleAction

    def evaluate(self, context: dict[str, int | float]) -> bool:
        """所有条件是否都满足。"""
        return all(condition.evaluate(context) for condition in self.conditions)


@dataclass
class RuleEngine:
    """规则引擎：顺序评估规则列表，返回首个命中的动作。

    Attributes:
        rules: 规则列表，按优先级从高到低排列。
        default: 全部不命中时的默认动作。
    """

    rules: list[Rule] = field(default_factory=list)
    default: RuleAction = field(default_factory=RuleAction.no_action)

    def evaluate(self, context: dict[str, int | float]) -> RuleAction:
        """对敌方编成上下文评估全部规则。

        Args:
            context: 敌方舰种计数，如 {"BB": 2, "CV": 1, "DD": 3, "total": 6}。

        Returns:
            首个命中规则的动作，或 default。
        """
        for rule in self.rules:
            if not rule.evaluate(context):
                continue
            _log.debug(
                '[COMBAT] 编成规则命中 → {}：条件={}',
                rule.action.result.name,
                [(condition.field, condition.op, condition.value) for condition in rule.conditions],
            )
            return rule.action
        return self.default

    @classmethod
    def from_legacy_rules(cls, legacy_rules: list[list]) -> RuleEngine:
        """从旧版 enemy_rules 格式构建。

        Args:
            legacy_rules: 每项为 [条件字符串, 动作]，动作可以是 retreat、detour
                或阵型编号。

        Returns:
            构建好的规则引擎。
        """
        rules: list[Rule] = []
        for item in legacy_rules:
            condition_text, action_value = item[0], item[1]
            rules.append(
                Rule(
                    conditions=_parse_legacy_condition(condition_text),
                    action=_parse_action_value(action_value),
                )
            )
        return cls(rules=rules)

    @classmethod
    def from_formation_rules(cls, formation_rules: list[list]) -> RuleEngine:
        """从旧版 enemy_formation_rules 格式构建。

        这类规则不比较数字，而是匹配敌方阵型名称，内部转成以阵型名为字段的
        等值条件。

        Args:
            formation_rules: 每项为 [阵型名称, 动作]。

        Returns:
            构建好的规则引擎。
        """
        rules: list[Rule] = []
        for item in formation_rules:
            formation_name, action_value = item[0], item[1]
            rules.append(
                Rule(
                    conditions=[Condition(field=f'_formation:{formation_name}', op='==', value=1)],
                    action=_parse_action_value(action_value),
                )
            )
        return cls(rules=rules)

    def evaluate_formation(self, enemy_formation: str) -> RuleAction:
        """评估敌方阵型规则。

        Args:
            enemy_formation: 敌方阵型名称。

        Returns:
            阵型规则的动作。
        """
        return self.evaluate({f'_formation:{enemy_formation}': 1})


# 匹配 "BB >= 2" 或 "CL + DD >= 1" 形式的条件片段。
_CONDITION_PIECE_RE = re.compile(
    r'([A-Z]{2,4}(?:\s*\+\s*[A-Z]{2,4})*)\s*'
    r'(>=|<=|>|<|==|!=)\s*(\d+(?:\.\d+)?)'
)
_CONDITION_SEPARATOR_RE = re.compile(r'\s+and\s+', re.IGNORECASE)
_CONDITION_ATOM_RE = re.compile(
    rf'(?:{_CONDITION_PIECE_RE.pattern}|\(\s*{_CONDITION_PIECE_RE.pattern}\s*\))'
)


def _parse_legacy_condition(condition_text: str) -> list[Condition]:
    """把旧格式条件字符串解析成条件列表。

    ``"(BB >= 2) and (CV > 0)"`` 拆成两个条件（AND 语义）。不支持 or，需要
    或关系时写成多条规则。``CL + DD >= 1`` 表示多个舰种求和。

    Args:
        condition_text: 旧格式条件字符串。

    Returns:
        解析出的条件列表。

    Raises:
        ValueError: 条件无法解析或含未知舰种代码。
    """
    conditions: list[Condition] = []
    normalized = re.sub(
        r'([<>!])\s*=\s*',
        r'\1=',
        condition_text.strip().upper(),
    )
    parts = _CONDITION_SEPARATOR_RE.split(normalized)
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f"无法解析规则条件: '{condition_text}'")
    for part in parts:
        atom = part.strip()
        if _CONDITION_ATOM_RE.fullmatch(atom) is None:
            raise ValueError(f"无法解析规则条件: '{condition_text}'")
        match = _CONDITION_PIECE_RE.search(atom)
        if match is None:
            raise ValueError(f"无法解析规则条件: '{condition_text}'")
        field_expression, operator, value_text = match.groups()
        value = float(value_text) if '.' in value_text else int(value_text)
        field_parts = field_expression.split('+')
        field_codes = [
            _LEGACY_RULE_FIELD_ALIASES.get(part.strip(), part.strip()) for part in field_parts
        ]
        if any(part.strip() == 'BG' for part in field_parts):
            raise ValueError('BG 舰种代码语义有歧义：大巡请使用 CBG，导战请使用 BBG')
        unknown_codes = [code for code in field_codes if code not in _RULE_FIELD_CODES]
        if unknown_codes:
            raise ValueError(f'未知舰种代码: {unknown_codes!r}')
        conditions.append(Condition(field='+'.join(field_codes), op=operator, value=value))
    return conditions


def _parse_action_value(action_value: str | int) -> RuleAction:
    """把旧格式的动作值转成 RuleAction。

    Args:
        action_value: retreat、detour 或阵型编号。

    Returns:
        对应的动作。

    Raises:
        ValueError: 动作值无法识别。
    """
    if isinstance(action_value, int) and not isinstance(action_value, bool):
        return RuleAction.set_formation(Formation(action_value))
    if isinstance(action_value, str):
        action_lower = action_value.strip().lower()
        if action_lower == 'retreat':
            return RuleAction.retreat()
        if action_lower == 'detour':
            return RuleAction.detour()
        try:
            return RuleAction.set_formation(Formation(int(action_value)))
        except (ValueError, KeyError):
            pass
    raise ValueError(f'无法识别的动作值: {action_value!r}')


__all__ = [
    'Condition',
    'Rule',
    'RuleAction',
    'RuleEngine',
    'RuleResult',
]
