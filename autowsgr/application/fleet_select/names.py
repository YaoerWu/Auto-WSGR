"""模块功能：维护舰名表、别名与同船身份归一化。

上层调用：
- application.fleet_select：编队规划与换船流程用它比对 OCR 读到的舰名。
- application.controller：识别到舰名文本后，用同一套归一化口径清洗再交给上层。

下层依赖：
- common.system.files：安全加载 resources/data/shipnames.yaml。

边界：只维护舰名数据与纯文本归一化，不读取图像、不认识页面、不判断阵容规则。
用户别名通过 ContextVar 做请求级覆盖，不修改进程级舰名表。
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from autowsgr.common.system.files import load_yaml


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


_LOCAL_SHIPNAME_ALIASES: ContextVar[Mapping[str, str]] = ContextVar(
    'local_shipname_aliases',
    default=MappingProxyType({}),
)


class _ShipNameList(list[str]):
    """Base names plus request-local aliases during OCR."""

    def __iter__(self) -> Iterator[str]:
        yield from super().__iter__()
        for alias in _LOCAL_SHIPNAME_ALIASES.get():
            if list.__contains__(self, alias):
                continue
            yield alias

    def __contains__(self, value: object) -> bool:
        return super().__contains__(value) or (
            isinstance(value, str) and value in _LOCAL_SHIPNAME_ALIASES.get()
        )


SHIP_NAME_SUFFIXES: tuple[str, ...] = ('·改',)
_SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')


def process_dict(d: dict) -> list[str]:
    """处理 YAML 数据，提取舰船名称列表。

    预期输入格式为：
    ```yaml
    ships:
      - 舰船A
      - 舰船B
      # ...
    ```

    Parameters
    ----------
    d:
        从 YAML 文件加载的原始数据字典。
    Returns
    -------
        舰船名称列表。
    """
    result = []
    for v in d.values():
        result.extend(v)
    return result


# 舰名表是换船业务的静态资产，随本模块一起维护，放在仓库资源目录。
_DATA_ROOT = Path(__file__).resolve().parents[3] / 'resources' / 'data'
_SHIPNAME_PATH = _DATA_ROOT / 'shipnames.yaml'
_BASE_SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names)
    for group_id, names in load_yaml(_SHIPNAME_PATH, allowed_root=_DATA_ROOT).items()
}
SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names) for group_id, names in _BASE_SHIPNAME_GROUPS.items()
}
_EXTRA_SHIPNAMES: list[str] = []
_SHIPNAME_TO_GROUP: dict[str, str] = {
    name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names
}
SHIPNAMES: list[str] = _ShipNameList(process_dict(SHIPNAME_GROUPS))

# 决战中出现的非舰船名卡片（副官技能等）
DECISIVE_SKILL_NAMES: list[str] = ['长跑训练', '肌肉记忆', '黑科技']


def update_shipnames(extra: list[str]) -> None:
    """将额外名称添加到 :data:`SHIPNAMES` 前端（去重）。

    典型场景：决战开始时把 ``config.level1 + config.level2 + DECISIVE_SKILL_NAMES``
    合并进全局列表，后续 OCR 识别无需再临时拼接候选集。

    Parameters
    ----------
    extra:
        要添加的额外名称列表。
    """
    existing = set(_EXTRA_SHIPNAMES)
    for name in extra:
        if name not in existing:
            _EXTRA_SHIPNAMES.append(name)
            existing.add(name)
    _rebuild_shipnames()


def get_ship_name_group_id(name: str) -> str | None:
    """返回舰名所属的 ``No.xxx`` 舰船组。"""
    name = _LOCAL_SHIPNAME_ALIASES.get().get(name, name)
    group_id = _SHIPNAME_TO_GROUP.get(name)
    return group_id if group_id is not None and group_id.startswith('No.') else None


def is_standard_ship_name(name: str) -> bool:
    """判断名称是否来自内置舰名表，而非用户别名。"""
    return any(name in names for names in _BASE_SHIPNAME_GROUPS.values())


def get_ship_name_variants(name: str) -> list[str]:
    """返回同一艘船的全部名称，未登记名称只返回自身。"""
    group_id = get_ship_name_group_id(name)
    return list(SHIPNAME_GROUPS[group_id]) if group_id is not None else [name]


def canonical_ship_name(name: str) -> str:
    """将同组名称统一为该舰船组的第一个名称。"""
    return get_ship_name_variants(name)[0]


def normalize_ship_name(value: object) -> str | None:
    """统一舰名文本，处理空值、登记别名和明确的显示后缀。"""
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    normalized = canonical_ship_name(normalized)
    for suffix in SHIP_NAME_SUFFIXES:
        normalized = normalized.removesuffix(suffix)
    normalized = _SHIP_ALIAS_SUFFIX_RE.sub('', normalized).strip()
    if not normalized:
        return None
    return canonical_ship_name(normalized)


def ship_name_identity(value: object) -> str | None:
    """返回用于同船唯一性判断的稳定身份。"""
    normalized = normalize_ship_name(value)
    if normalized is None:
        return None
    return get_ship_name_group_id(normalized) or normalized


def expand_ship_name_candidates(candidates: list[str]) -> list[str]:
    """将候选舰名扩展为每个候选所在舰船组的全部名称。"""
    expanded: list[str] = []
    for candidate in candidates:
        for name in get_ship_name_variants(candidate):
            if name not in expanded:
                expanded.append(name)
    return expanded


# ── OCR 纠错与模糊匹配 ──────────────────────────────────────────────────────

# 系统纠错规则由项目维护，目标必须是 shipnames.yaml 里的标准舰名。
SHIP_NAME_CORRECTIONS: dict[str, str] = {
    '鲍鱼': '鲃鱼',
    '鳟盹': '鳞鲀',
    '296': 'M-296',
    '维内托': '维托里奥·维内托',
    'IA': 'IIIA',
}

# 间隔号常被 OCR 读成冒号，只修正两个汉字之间的那一个。
_CJK_COLON_SEPARATOR_RE = re.compile(r'(?<=[\u3400-\u9fff]):(?=[\u3400-\u9fff])')


def apply_ship_name_corrections(text: str) -> str:
    """按已知错字和字符习惯纠正 OCR 读到的舰名原文。

    Args:
        text: OCR 读到的舰名原始文本。

    Returns:
        纠正后的文本；命中已知错字时直接返回对应的标准舰名。
    """
    for wrong, standard in SHIP_NAME_CORRECTIONS.items():
        if wrong in text:
            return standard

    # 潜艇名的 U 常被读成 0，例如 U-1206 -> 01206。
    if text.startswith('0') and sum(char.isdigit() for char in text) >= 3:
        text = 'U' + text[1:]
    return _CJK_COLON_SEPARATOR_RE.sub('·', text)


def fuzzy_match_ship_name(
    text: str,
    candidates: list[str],
    *,
    threshold: int = 3,
) -> str | None:
    """在候选舰名里按编辑距离找出唯一最接近的一个。

    单字和极短舰名的容错必须收紧，否则任何短词都能凑上一个舰名。

    Args:
        text: 已纠正过的舰名文本。
        candidates: 候选舰名清单，同组别名会一起参与比较。
        threshold: 长舰名允许的最大编辑距离。

    Returns:
        距离最近且不超过阈值的候选；没有候选、距离过远或最近的候选不唯一时为 None。
    """
    unique_candidates = expand_ship_name_candidates(candidates)
    if not text or not unique_candidates:
        return None

    if len(text) == 1:
        effective_threshold = 0
    elif len(text) <= 3:
        effective_threshold = min(threshold, 1)
    else:
        effective_threshold = threshold

    nearest: str | None = None
    nearest_distance = effective_threshold + 1
    tied = False
    for candidate in unique_candidates:
        distance = _edit_distance(text, candidate)
        if distance < nearest_distance:
            nearest, nearest_distance, tied = candidate, distance, False
        elif distance == nearest_distance:
            tied = True
    return None if tied else nearest


def set_ship_name_aliases(aliases: Mapping[str, str]) -> None:
    """重置用户自定义名，并追加到目标标准舰名所在的舰船组。"""
    SHIPNAME_GROUPS.clear()
    SHIPNAME_GROUPS.update(
        {group_id: list(names) for group_id, names in _BASE_SHIPNAME_GROUPS.items()},
    )
    _rebuild_shipnames()
    for alias, standard_name in aliases.items():
        group_id = get_ship_name_group_id(standard_name)
        if group_id is not None and alias not in SHIPNAME_GROUPS[group_id]:
            SHIPNAME_GROUPS[group_id].append(alias)
    _rebuild_shipnames()


def get_active_ship_name_aliases() -> Mapping[str, str]:
    """Return aliases active in the current request context."""
    return _LOCAL_SHIPNAME_ALIASES.get()


@contextmanager
def ship_name_aliases_scope(aliases: Mapping[str, str]) -> Iterator[None]:
    """Overlay aliases for one task without changing process-global names."""
    normalized = {
        alias.strip(): standard_name.strip()
        for alias, standard_name in aliases.items()
        if isinstance(alias, str)
        and isinstance(standard_name, str)
        and alias.strip()
        and standard_name.strip()
    }
    token = _LOCAL_SHIPNAME_ALIASES.set(MappingProxyType(normalized))
    try:
        yield
    finally:
        _LOCAL_SHIPNAME_ALIASES.reset(token)


def _rebuild_shipnames() -> None:
    """原地刷新扁平舰名列表和舰名到分组的索引。"""
    _SHIPNAME_TO_GROUP.clear()
    _SHIPNAME_TO_GROUP.update(
        {name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names},
    )
    grouped_names = process_dict(SHIPNAME_GROUPS)
    SHIPNAMES[:] = list(dict.fromkeys([*_EXTRA_SHIPNAMES, *grouped_names]))


def _edit_distance(left: str, right: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离。"""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_char != right_char),
                ),
            )
        previous = current
    return previous[-1]


__all__ = [
    'DECISIVE_SKILL_NAMES',
    'SHIPNAMES',
    'SHIPNAME_GROUPS',
    'SHIP_NAME_CORRECTIONS',
    'SHIP_NAME_SUFFIXES',
    'apply_ship_name_corrections',
    'canonical_ship_name',
    'expand_ship_name_candidates',
    'fuzzy_match_ship_name',
    'get_active_ship_name_aliases',
    'get_ship_name_group_id',
    'get_ship_name_variants',
    'is_standard_ship_name',
    'normalize_ship_name',
    'process_dict',
    'set_ship_name_aliases',
    'ship_name_aliases_scope',
    'ship_name_identity',
    'update_shipnames',
]
