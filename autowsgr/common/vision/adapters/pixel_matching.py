"""模块功能：组合 NumPy 采样和颜色规则，完成像素签名匹配。

上层调用：
- common.vision.service：取用像素签名匹配入口。
- common.vision.adapters：重新修饰像素匹配能力供 service 调用。

下层依赖：
- NumPy：提供数组运算。
- common.vision.numpy.executor：提供像素采样和坐标换算。
- common.vision.adapters.template_matching：提供 ROI 模型。
- common.vision.config 和 common.system.logger：提供容差默认值和日志对象。

边界：不负责设备截图、页面状态、模板加载或业务领域识别规则。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

import numpy

from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision.adapters.template_matching import ROI
from autowsgr.common.vision.config import NUMPY_DEFAULT_PIXEL_TOLERANCE
from autowsgr.common.vision.numpy.executor import NumpyExecutor


_log = get_logger('vision.pixel')


_EXECUTOR = NumpyExecutor()


# ── 像素规则模型 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Color:
    """一个 RGB 颜色。"""

    red: int
    green: int
    blue: int

    def distance(self, other: Color) -> float:
        """计算两个 RGB 颜色的欧几里得距离。

        Args:
            other: 用于比较的 RGB 颜色。

        Returns:
            两个颜色之间的距离。
        """
        return math.sqrt(
            (self.red - other.red) ** 2
            + (self.green - other.green) ** 2
            + (self.blue - other.blue) ** 2,
        )

    def near(self, other: Color, tolerance: float = NUMPY_DEFAULT_PIXEL_TOLERANCE) -> bool:
        """判断两个颜色是否在容差范围内。

        Args:
            other: 用于比较的 RGB 颜色。
            tolerance: 允许的颜色距离。

        Returns:
            颜色距离不超过容差时返回 True。
        """
        return self.distance(other) <= tolerance

    def as_tuple(self) -> tuple[int, int, int]:
        """返回 RGB 整数元组。

        Returns:
            (red, green, blue) 元组。
        """
        return self.red, self.green, self.blue


@dataclass(frozen=True, slots=True)
class PixelRule:
    """一个相对坐标上的颜色约束。"""

    x: float
    y: float
    color: Color
    tolerance: float = NUMPY_DEFAULT_PIXEL_TOLERANCE

    def __post_init__(self) -> None:
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError('像素规则坐标必须位于 [0, 1]')
        if self.tolerance < 0.0:
            raise ValueError('像素规则容差不能为负数')


class MatchStrategy(StrEnum):
    """像素签名的匹配策略。"""

    ALL = 'all'
    ANY = 'any'
    COUNT = 'count'


@dataclass(frozen=True, slots=True)
class PixelSignature:
    """一组用于识别页面或状态的像素规则。"""

    name: str
    rules: tuple[PixelRule, ...]
    strategy: MatchStrategy = MatchStrategy.ALL
    threshold: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, 'rules', tuple(self.rules))


@dataclass(frozen=True, slots=True)
class CompositePixelSignature:
    """多个像素签名的 OR 组合。"""

    name: str
    signatures: tuple[PixelSignature, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'signatures', tuple(self.signatures))

    def __len__(self) -> int:
        """返回子签名数量。"""
        return len(self.signatures)


@dataclass(frozen=True, slots=True)
class PixelDetail:
    """一条像素规则的检测结果。"""

    rule: PixelRule
    actual: Color
    distance: float
    matched: bool


@dataclass(frozen=True, slots=True)
class PixelMatchResult:
    """像素签名匹配结果。

    Attributes:
        matched: 本次匹配是否命中。
        signature_name: 调用方给出的签名名；组合签名时是组合名。
        matched_count: 命中的签名数量；单签名时只有 0 或 1。
        total_count: 参与匹配的签名数量；单签名时为规则条数。
        details: 逐规则采样详情，仅 with_details 为真时填充。
        matched_signature: 命中的签名名；组合签名时是命中的子签名，未命中为 None。
    """

    matched: bool
    signature_name: str
    matched_count: int
    total_count: int
    details: tuple[PixelDetail, ...] = field(default_factory=tuple)
    matched_signature: str | None = None

    def __bool__(self) -> bool:
        return self.matched

    @property
    def ratio(self) -> float:
        """返回命中规则占全部规则的比例；规则总数为零时为 0。"""
        return self.matched_count / self.total_count if self.total_count else 0.0


# ── 像素匹配 ────────────────────────────────────────────────────────────────


def match_pixels(
    image: numpy.ndarray,
    signature: (
        PixelSignature
        | CompositePixelSignature
        | Sequence[PixelSignature | CompositePixelSignature]
    ),
    *,
    roi: ROI | Sequence[ROI | None] | None = None,
    with_details: bool = False,
) -> list[PixelMatchResult]:
    """执行一次完整的 ROI 和 NumPy 像素签名匹配流程。

    同一帧内可以依次匹配多组签名：传序列时每个元素独立匹配，roi 传序列时与签名
    一一对应；单个签名或单个 roi 时按标量处理。

    Args:
        image: 待检查的 RGB 图片数组。
        signature: 单个像素签名、签名组合，或需要逐个匹配的一组签名。
        roi: 共享检查区域，或与签名一一对应的区域序列。
        with_details: 是否返回每条规则的采样详情。

    Returns:
        按签名顺序排列的匹配结果列表。
    """
    # 1. 先规范化签名和区域，让标量输入与序列输入走同一条路径。
    signatures: tuple[PixelSignature | CompositePixelSignature, ...]
    if isinstance(signature, (PixelSignature, CompositePixelSignature)):
        signatures = (signature,)
    elif isinstance(signature, Sequence) and not isinstance(signature, (str, bytes)):
        signatures = tuple(signature)
        if not signatures:
            raise ValueError('签名序列不能为空')
        if not all(
            isinstance(item, (PixelSignature, CompositePixelSignature)) for item in signatures
        ):
            raise TypeError('签名序列中的元素必须是 PixelSignature 或 CompositePixelSignature')
    else:
        raise TypeError('signature 必须是 PixelSignature、CompositePixelSignature 或签名序列')

    regions: tuple[ROI | None, ...]
    if roi is None or isinstance(roi, ROI):
        regions = (roi,) * len(signatures)
    elif isinstance(roi, Sequence) and not isinstance(roi, (str, bytes)):
        regions = tuple(roi)
        if len(regions) != len(signatures):
            raise ValueError('roi 序列长度必须与签名数量一致')
        if not all(item is None or isinstance(item, ROI) for item in regions):
            raise TypeError('roi 序列中的元素必须是 ROI 或 None')
    else:
        raise TypeError('roi 必须是 ROI、ROI 序列或 None')

    # 2. 同一帧内按签名顺序逐个匹配，每个签名只裁自己那块区域。
    match_results = [
        _match_one(image, item, roi=region, with_details=with_details)
        for item, region in zip(signatures, regions, strict=True)
    ]
    _log.debug(
        '[VISION] 像素匹配 → 匹配结果：signatures={!r}, matched_signatures={!r}',
        [result.signature_name for result in match_results],
        [result.matched_signature for result in match_results],
    )
    return match_results


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _match_one(
    image: numpy.ndarray,
    signature: PixelSignature | CompositePixelSignature,
    *,
    roi: ROI | None,
    with_details: bool,
) -> PixelMatchResult:
    """在限定区域内匹配单个签名或签名组合。"""
    # 1. 先限制检查区域，避免像素规则读取无关画面。
    source_image = roi.crop(image) if roi is not None else image

    # 2. 组合签名按顺序尝试，单个签名直接执行规则判定。
    if isinstance(signature, CompositePixelSignature):
        return _match_composite(source_image, signature, with_details=with_details)
    return _match_signature(source_image, signature, with_details=with_details)


def _match_signature(
    image: numpy.ndarray,
    signature: PixelSignature,
    *,
    with_details: bool,
) -> PixelMatchResult:
    """按签名策略判定单个像素签名的全部规则。"""
    rules = signature.rules
    # 空规则只在 COUNT 阈值为零时命中，避免无依据地确认状态。
    if not rules:
        matched = signature.strategy is not MatchStrategy.COUNT or signature.threshold == 0
        return PixelMatchResult(
            matched,
            signature.name,
            0,
            0,
            (),
            signature.name if matched else None,
        )

    # 1. 批量采样后统一计算颜色距离，保持规则顺序与详情顺序一致。
    actual = _EXECUTOR.sample_pixels(image, [(rule.x, rule.y) for rule in rules])
    expected = numpy.asarray([rule.color.as_tuple() for rule in rules], dtype=numpy.float32)
    tolerances = numpy.asarray([rule.tolerance for rule in rules], dtype=numpy.float32)
    distances = numpy.sqrt(
        numpy.sum((actual.astype(numpy.float32) - expected) ** 2, axis=1),
    )
    matched_flags = distances <= tolerances
    matched_count = int(matched_flags.sum())

    # 2. 按策略把命中条数换算成整体结论。
    matched = {
        MatchStrategy.ALL: matched_count == len(rules),
        MatchStrategy.ANY: matched_count > 0,
        MatchStrategy.COUNT: matched_count >= signature.threshold,
    }[signature.strategy]
    details = (
        tuple(
            PixelDetail(
                rule=rule,
                actual=Color(*(int(channel) for channel in actual[index])),
                distance=float(distances[index]),
                matched=bool(matched_flags[index]),
            )
            for index, rule in enumerate(rules)
        )
        if with_details
        else ()
    )
    return PixelMatchResult(
        matched,
        signature.name,
        matched_count,
        len(rules),
        details,
        signature.name if matched else None,
    )


def _match_composite(
    image: numpy.ndarray,
    composite: CompositePixelSignature,
    *,
    with_details: bool,
) -> PixelMatchResult:
    """依次匹配子签名并在首个命中时返回。

    Args:
        image: 已经完成 ROI 裁切的 RGB 图片数组。
        composite: 按优先级排列的像素签名组合。
        with_details: 是否保留每条规则的采样详情。

    Returns:
        首个命中的组合结果，或包含全部失败详情的未命中结果。命中结果用
        matched_signature 带出命中的子签名名，调用方据此区分是哪个候选。
    """
    details: list[PixelDetail] = []
    for signature in composite.signatures:
        signature_result = _match_signature(image, signature, with_details=with_details)
        if with_details:
            details.extend(signature_result.details)
        # 组合签名只需要第一个命中结果，后续签名不会改变业务结论。
        if signature_result.matched:
            return PixelMatchResult(
                True,
                composite.name,
                1,
                len(composite.signatures),
                tuple(details),
                signature.name,
            )
    return PixelMatchResult(
        False,
        composite.name,
        0,
        len(composite.signatures),
        tuple(details),
    )


__all__ = [
    'Color',
    'CompositePixelSignature',
    'MatchStrategy',
    'PixelDetail',
    'PixelMatchResult',
    'PixelRule',
    'PixelSignature',
    'match_pixels',
]
