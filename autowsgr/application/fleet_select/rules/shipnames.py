"""模块功能：维护舰名表、别名与同船身份归一化。

上层调用：
- business：换船任务在规划编队前注入用户别名，并读取本模块的舰名表。

下层依赖：
- common.system.files：安全加载 resources/data/shipnames.yaml。

边界：只维护舰名数据与纯文本归一化，不读取图像、不认识页面、不判断阵容规则。
启动期用户别名由 load_ship_name_aliases 写进进程级舰名表；单次任务内的额外别名
走 apply_ship_name_aliases 的 ContextVar 覆盖，退出后不残留。
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


# ── 舰名数据 ────────────────────────────────────────────────────────────────

# 舰名表是换船业务的静态资产，随本模块一起维护，放在仓库资源目录。
_DATA_ROOT = Path(__file__).resolve().parents[4] / 'resources' / 'data'
_SHIPNAME_PATH = _DATA_ROOT / 'shipnames.yaml'

SHIP_NAME_SUFFIXES: tuple[str, ...] = ('·改',)
_SHIP_ALIAS_SUFFIX_RE = re.compile(r'\s*[（(][^（）()]*[)）]\s*$')

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

# 决战中出现的非舰船名卡片（副官技能等）。
DECISIVE_SKILL_NAMES: list[str] = ['长跑训练', '肌肉记忆', '黑科技']


# ── 舰名表与运行期索引 ──────────────────────────────────────────────────────


# 基础舰名表在导入时加载一次，运行期只读；下面的进程级表由用户别名装载重建。
_BASE_SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names)
    for group_id, names in load_yaml(_SHIPNAME_PATH, allowed_root=_DATA_ROOT).items()
}
SHIPNAME_GROUPS: dict[str, list[str]] = {
    group_id: list(names) for group_id, names in _BASE_SHIPNAME_GROUPS.items()
}
_SHIPNAME_TO_GROUP: dict[str, str] = {
    name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names
}


_LOCAL_SHIPNAME_ALIASES: ContextVar[Mapping[str, str]] = ContextVar(
    'local_shipname_aliases',
    default=MappingProxyType({}),
)


class _ShipNameList(list[str]):
    """在基础舰名表上叠加请求级用户别名的舰名列表。

    迭代和成员判断都会带上当前 ContextVar 里的别名；底层列表仍只存基础舰名。
    """

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


SHIPNAMES: list[str] = _ShipNameList([name for names in SHIPNAME_GROUPS.values() for name in names])


# ── 舰名归一化 ──────────────────────────────────────────────────────────────


def get_ship_name_group_id(ship_name: str) -> str | None:
    """返回舰名所属的 No.xxx 舰船组。

    Args:
        ship_name: 已归一化的标准舰名。

    Returns:
        形如 No.123 的舰船组编号；不是登记舰船时为 None。
    """
    resolved = _LOCAL_SHIPNAME_ALIASES.get().get(ship_name, ship_name)
    group_id = _SHIPNAME_TO_GROUP.get(resolved)
    return group_id if group_id is not None and group_id.startswith('No.') else None


def is_standard_ship_name(ship_name: str) -> bool:
    """判断名称是否来自内置舰名表，而非用户别名。

    Args:
        ship_name: 待判断的舰名。

    Returns:
        命中基础舰名表时为 True。
    """
    return any(ship_name in names for names in _BASE_SHIPNAME_GROUPS.values())


def _get_ship_name_variants(ship_name: str) -> list[str]:
    """返回同一艘船的全部名称，未登记名称只返回自身。

    Args:
        ship_name: 已归一化的标准舰名。

    Returns:
        该舰船组内的全部名称；不是登记舰船时只含自身。
    """
    group_id = get_ship_name_group_id(ship_name)
    return list(SHIPNAME_GROUPS[group_id]) if group_id is not None else [ship_name]


def _get_canonical_ship_name(ship_name: str) -> str:
    """将同组名称统一为该舰船组的第一个名称。

    Args:
        ship_name: 待统一的标准舰名或同组别名。

    Returns:
        该舰船组的首个名称；未登记时原样返回。
    """
    return _get_ship_name_variants(ship_name)[0]


def normalize_ship_name(ship_name: object) -> str | None:
    """统一舰名文本，处理空值、登记别名和明确的显示后缀。

    Args:
        ship_name: 待归一的舰名原文，允许是任意类型，非字符串会被转成字符串。

    Returns:
        归一化后的标准舰名；空值、空文本或只剩后缀时为 None。
    """
    if ship_name is None:
        return None

    normalized = str(ship_name).strip()
    if not normalized:
        return None

    normalized = _get_canonical_ship_name(normalized)
    for suffix in SHIP_NAME_SUFFIXES:
        normalized = normalized.removesuffix(suffix)
    normalized = _SHIP_ALIAS_SUFFIX_RE.sub('', normalized).strip()
    if not normalized:
        return None
    return _get_canonical_ship_name(normalized)


def get_ship_name_identity(ship_name: object) -> str | None:
    """返回用于同船唯一性判断的稳定身份。

    Args:
        ship_name: 待求身份的舰名原文。

    Returns:
        舰船组编号或标准舰名；无法归一化时为 None。
    """
    normalized = normalize_ship_name(ship_name)
    if normalized is None:
        return None
    return get_ship_name_group_id(normalized) or normalized


def build_ship_name_candidates(candidates: list[str]) -> list[str]:
    """将候选舰名扩展为每个候选所在舰船组的全部名称。"""
    expanded: list[str] = []
    for candidate in candidates:
        for name in _get_ship_name_variants(candidate):
            if name not in expanded:
                expanded.append(name)
    return expanded


# ── OCR 纠错与模糊匹配 ──────────────────────────────────────────────────────


def correct_ship_name(text: str) -> str:
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


def select_ship_name(
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
    unique_candidates = build_ship_name_candidates(candidates)
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


# ── 用户别名 ────────────────────────────────────────────────────────────────


def load_ship_name_aliases(aliases: Mapping[str, str]) -> None:
    """用用户别名重建进程级舰名表。

    先恢复成基础舰名表，再把每个别名追加到目标标准舰名所在的舰船组。

    Args:
        aliases: 用户别名到标准舰名的映射；传空映射表示清空用户别名。
    """
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
    """返回当前请求上下文生效的用户舰名别名。

    Returns:
        别名到标准舰名的只读映射；不在作用域内时为空映射。
    """
    return _LOCAL_SHIPNAME_ALIASES.get()


@contextmanager
def apply_ship_name_aliases(aliases: Mapping[str, str]) -> Iterator[None]:
    """在一段作用域内叠加用户舰名别名，不修改进程级舰名表。

    Args:
        aliases: 用户别名到标准舰名的映射。

    Yields:
        作用域内别名生效，退出时自动恢复。
    """
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


# ── 舰名表维护 ──────────────────────────────────────────────────────────────


def _rebuild_shipnames() -> None:
    """原地刷新扁平舰名列表和舰名到分组的索引。

    进程级表被 load_ship_name_aliases 改动后必须调用一次，保证 SHIPNAMES 与
    _SHIPNAME_TO_GROUP 始终和 SHIPNAME_GROUPS 保持一致。
    """
    _SHIPNAME_TO_GROUP.clear()
    _SHIPNAME_TO_GROUP.update(
        {name: group_id for group_id, names in SHIPNAME_GROUPS.items() for name in names},
    )
    names = [name for group in SHIPNAME_GROUPS.values() for name in group]
    SHIPNAMES[:] = list(dict.fromkeys(names))


def _edit_distance(left: str, right: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离。

    Args:
        left: 待比较的左串。
        right: 待比较的右串。

    Returns:
        把左串改成右串所需的最少单字符增删改次数。
    """
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
    'apply_ship_name_aliases',
    'build_ship_name_candidates',
    'correct_ship_name',
    'get_active_ship_name_aliases',
    'get_ship_name_group_id',
    'get_ship_name_identity',
    'is_standard_ship_name',
    'load_ship_name_aliases',
    'normalize_ship_name',
    'select_ship_name',
]
