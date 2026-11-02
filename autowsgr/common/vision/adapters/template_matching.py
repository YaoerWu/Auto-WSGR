"""模块功能：组合 ROI 裁切、模板加载、缩放和 OpenCV 匹配。

上层调用：
- common.vision.service：取用模板匹配入口。
- common.vision.adapters：重新修饰模板匹配能力供 service 调用。

下层依赖：
- OpenCV：提供模板匹配算子。
- NumPy：提供数组类型。
- common.vision.config：提供模板置信度和来源分辨率。
- common.vision.opencv.executor：提供图片加载和匹配执行器。

边界：不负责设备截图、模板缓存、页面状态或业务领域识别规则。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision.config import (
    OPENCV_TEMPLATE_CONFIDENCE,
    OPENCV_TEMPLATE_SOURCE_RESOLUTION,
)
from autowsgr.common.vision.opencv.executor import OpenCVExecutor


if TYPE_CHECKING:
    import numpy


_log = get_logger('vision.template')


# 「差一点就中」的界线：命中阈值的一定比例。低于它说明画面里压根没这个东西，
# 属于正常噪声；落在它和阈值之间说明画面像但没够，是排查识别失败的关键线索。
_NEAR_MISS_RATIO = 0.9

_EXECUTOR = OpenCVExecutor()


# ── 模板识别结果模型 ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ROI:
    """以相对坐标描述的矩形区域。"""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.x1 < self.x2 <= 1.0:
            raise ValueError('ROI 横坐标必须满足 0 <= x1 < x2 <= 1')
        if not 0.0 <= self.y1 < self.y2 <= 1.0:
            raise ValueError('ROI 纵坐标必须满足 0 <= y1 < y2 <= 1')

    def to_absolute(self, width: int, height: int) -> tuple[int, int, int, int]:
        """将相对坐标转换为图片像素坐标。

        Args:
            width: 图片宽度，单位为像素。
            height: 图片高度，单位为像素。

        Returns:
            (x1, y1, x2, y2) 像素坐标元组。
        """
        return (
            int(self.x1 * width),
            int(self.y1 * height),
            int(self.x2 * width),
            int(self.y2 * height),
        )

    def crop(self, image: numpy.ndarray) -> numpy.ndarray:
        """从图片中裁切 ROI。

        Args:
            image: 待裁切的图片数组。

        Returns:
            裁切后的图片副本。
        """
        height, width = image.shape[:2]
        x1, y1, x2, y2 = self.to_absolute(width, height)
        return image[y1:y2, x1:x2].copy()


@dataclass(frozen=True, slots=True)
class Template:
    """一张已加载的模板图片。"""

    name: str
    relative_path: str
    image: numpy.ndarray
    source_resolution: tuple[int, int] = OPENCV_TEMPLATE_SOURCE_RESOLUTION


@dataclass(frozen=True, slots=True)
class TemplateMatchResult:
    """一次模板匹配结果。

    Attributes:
        matched: 是否达到命中阈值。
        score: 匹配得分。
        location: 命中模板在原图上的左上角像素坐标。
        template_path: 模板在模板根目录下的相对路径。
        roi: 本次使用的搜索区域。
        center: 命中模板的归一化中心，未命中时为空；调用方可直接用作点击落点。
    """

    matched: bool
    score: float
    location: tuple[int, int] | None
    template_path: str
    roi: ROI | None = None
    center: tuple[float, float] | None = None


# ── 模板加载与匹配 ──────────────────────────────────────────────────────────


def load_template(
    relative_path: str | Path,
    *,
    name: str | None = None,
    source_resolution: tuple[int, int] = OPENCV_TEMPLATE_SOURCE_RESOLUTION,
) -> Template:
    """加载模板图片并构造模板数据。

    Args:
        relative_path: 模板根目录下的相对路径。
        name: 可选的模板业务名称，默认使用文件名。
        source_resolution: 模板截图分辨率，按 (width, height) 提供。

    Returns:
        已加载的模板数据。

    Raises:
        ValueError: 路径不是模板根目录下的相对路径。
    """
    # 1. 限制模板路径只能指向配置的资源根目录。
    relative = Path(relative_path)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('模板路径必须是 OPENCV_TEMPLATE_ROOT 下的相对路径')

    # 2. 读取模板图片并保留匹配所需的来源元数据。
    return Template(
        name=name or relative.stem,
        relative_path=relative.as_posix(),
        image=_EXECUTOR.load_image(relative),
        source_resolution=source_resolution,
    )


def match_template(
    image: numpy.ndarray,
    template: Template,
    *,
    roi: ROI | None = None,
    confidence: float = OPENCV_TEMPLATE_CONFIDENCE,
) -> TemplateMatchResult:
    """执行一次模板匹配并返回分数与位置。

    Args:
        image: 待搜索的 RGB 或灰度图片数组。
        template: 已加载的模板数据。
        roi: 可选的相对坐标搜索区域。
        confidence: 命中阈值，范围为 [0, 1]。

    Returns:
        包含命中状态、匹配分数、绝对位置和 ROI 的结果。

    Raises:
        ValueError: 置信度超出范围。
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError('匹配置信度必须位于 [0, 1]')

    # 1. 先确定搜索图片和原始尺寸，保证后续坐标使用同一基准。
    image_height, image_width = image.shape[:2]
    search = roi.crop(image) if roi is not None else image
    template_image = template.image
    source_width, source_height = template.source_resolution

    # 2. 截图分辨率变化时，按宽高比例缩放模板。
    template_height, template_width = template_image.shape[:2]
    if (image_width, image_height) != (source_width, source_height):
        scale_x = image_width / source_width
        scale_y = image_height / source_height
        template_image = _EXECUTOR.resize(
            template_image,
            max(1, round(template_width * scale_x)),
            max(1, round(template_height * scale_y)),
        )
        template_height, template_width = template_image.shape[:2]

    # 3. 执行 OpenCV 匹配，并把 ROI 内的位置还原到原图坐标。
    score, location = _EXECUTOR.match_template(search, template_image)
    if roi is not None:
        roi_x, roi_y, _, _ = roi.to_absolute(image_width, image_height)
        location = (location[0] + roi_x, location[1] + roi_y)

    # 4. 命中时给出模板中心的归一化坐标，供调用方直接点击。
    matched = score >= confidence
    center = None
    if matched:
        center = (
            round((location[0] + template_width / 2) / image_width, 4),
            round((location[1] + template_height / 2) / image_height, 4),
        )

    # 未命中是常态（一次扫描要问遍所有页面），只记「有事发生」的两种：命中，
    # 以及差一点就中——排查识别失败时，要能看出是画面真的变了，还是分数卡在
    # 阈值下面。
    if matched or score >= confidence * _NEAR_MISS_RATIO:
        _log.debug(
            '[VISION] 模板匹配 → {}：template_path={!r}, score={:.3f}, confidence={:.3f}',
            '命中' if matched else '差一点',
            template.relative_path,
            score,
            confidence,
        )
    return TemplateMatchResult(
        matched=matched,
        score=score,
        location=location,
        template_path=template.relative_path,
        roi=roi,
        center=center,
    )


def match_templates(
    image: numpy.ndarray,
    templates: Template | Sequence[Template],
    *,
    roi: ROI | Sequence[ROI | None] | None = None,
    confidence: float = OPENCV_TEMPLATE_CONFIDENCE,
) -> list[TemplateMatchResult]:
    """按顺序匹配单个或多个模板，并支持逐模板区域。

    Args:
        image: 待搜索的 RGB 或灰度图片数组。
        templates: 单个模板，或按业务优先级排列的模板序列。
        roi: 共享搜索区域，或与模板一一对应的区域序列。
        confidence: 命中阈值，范围为 [0, 1]。

    Returns:
        与输入模板顺序一致的匹配结果列表；单模板也返回长度为一的列表。
    """
    return [
        match_template(image, template, roi=item_roi, confidence=confidence)
        for template, item_roi in _template_roi_pairs(templates, roi)
    ]


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _template_roi_pairs(
    templates: Template | Sequence[Template],
    roi: ROI | Sequence[ROI | None] | None,
) -> tuple[tuple[Template, ROI | None], ...]:
    """规范化单模板、多模板以及共享或逐模板区域。"""
    if isinstance(templates, Template):
        if roi is not None and not isinstance(roi, ROI):
            raise TypeError('单模板的 roi 必须是 ROI 或 None')
        return ((templates, roi),)

    if isinstance(templates, (str, bytes)) or not isinstance(templates, Sequence):
        raise TypeError('templates 必须是 Template 或 Template 序列')
    items = tuple(templates)
    if not items:
        raise ValueError('templates 序列不能为空')
    if not all(isinstance(item, Template) for item in items):
        raise TypeError('templates 序列中的元素必须是 Template')

    if roi is None or isinstance(roi, ROI):
        rois = (roi,) * len(items)
    elif isinstance(roi, Sequence) and not isinstance(roi, (str, bytes)):
        rois = tuple(roi)
        if len(rois) != len(items):
            raise ValueError('roi 序列长度必须与 templates 序列一致')
        if not all(item is None or isinstance(item, ROI) for item in rois):
            raise TypeError('roi 序列中的元素必须是 ROI 或 None')
    else:
        raise TypeError('roi 必须是 ROI、ROI 序列或 None')
    return tuple(zip(items, rois, strict=True))


__all__ = [
    'ROI',
    'Template',
    'TemplateMatchResult',
    'load_template',
    'match_template',
    'match_templates',
]
