"""模块功能：组合 ROI 裁切、OpenCV 文本预处理和 OCR 识别。

上层调用：
- common.vision.service：取用 prepare_text、recognize_text 等通用识别入口。
- common.vision.adapters：重新修饰这里的能力供 service 调用。

下层依赖：
- OpenCV：提供文本预处理算子。
- FastOCR：提供文字检测和识别。
- common.vision.adapters.template_matching：提供 ROI 模型。
- common.vision.config、ocr 和 opencv：提供识别参数与执行器。

边界：不负责设备截图、领域文本修正、页面状态或业务候选规则的定义。
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from autowsgr.common.system.enums import StrEnum
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision.config import OPENCV_TEXT_BLUR_KERNEL, OPENCV_TEXT_SCALE
from autowsgr.common.vision.ocr.executor import OCRExecutor, TextDetection
from autowsgr.common.vision.opencv.executor import OpenCVExecutor


if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy

    from autowsgr.common.vision.adapters.template_matching import ROI


_log = get_logger('vision.ocr')


class RecognitionProfile(StrEnum):
    """FastOCR 识别模式。"""

    FULL = 'full'
    SINGLE_LINE = 'single_line'


# ── 共享执行器 ──────────────────────────────────────────────────────────────


_OPENCV = OpenCVExecutor()


# ── 文本预处理 ──────────────────────────────────────────────────────────────


def prepare_text(
    image: numpy.ndarray,
    *,
    scale: int = OPENCV_TEXT_SCALE,
    blur_kernel: int = OPENCV_TEXT_BLUR_KERNEL,
) -> numpy.ndarray:
    """执行通用 OCR 文本预处理。

    Args:
        image: 待处理的 RGB 或灰度图片数组。
        scale: 文本放大倍数。
        blur_kernel: 高斯模糊核边长，必须为正奇数。

    Returns:
        经过灰度、缩放、模糊、归一化和二值化的 RGB 数组。
    """
    # 空图片没有可处理内容，保持原输入避免制造无意义的 OpenCV 错误。
    if image.size == 0:
        return image

    # 1. 统一为灰度图并放大文字区域。
    gray = _OPENCV.to_gray(image)
    height, width = gray.shape[:2]
    gray = _OPENCV.resize(gray, width * scale, height * scale, interpolation='cubic')

    # 2. 平滑噪声、归一化对比度并生成二值图。
    gray = _OPENCV.blur(gray, blur_kernel)
    normalized = _OPENCV.normalize(gray)
    return _OPENCV.gray_to_rgb(_OPENCV.threshold(normalized))


# ── 文本解析 ────────────────────────────────────────────────────────────────


def parse_counter(text: str, max_value: int) -> int | None:
    """从 X/Y 文本中提取分子，允许 OCR 丢失分隔符。

    Args:
        text: OCR 返回的计数文本。
        max_value: 计数分母，用于识别丢失分隔符的文本。

    Returns:
        能够确认的分子；无法从无分隔符文本确认分母时返回 None。

    Raises:
        ValueError: 文本中没有可用数字，或分隔符前没有数字。
    """
    # 1. 优先读取明确的分隔符，避免把分母误认为分子。
    for separator in ('/', '|'):
        if separator in text:
            digits = ''.join(
                character for character in text.split(separator, 1)[0] if character.isdigit()
            )
            if digits:
                return int(digits)
            raise ValueError(f'分子部分无数字: "{text}"')

    # 2. OCR 可能丢失分隔符，只有能识别末尾分母时才拆分。
    digits = ''.join(character for character in text if character.isdigit())
    if not digits:
        raise ValueError(f'文本中无数字: "{text}"')

    prefixed_denominator = f'1{max_value}'
    if digits.endswith(prefixed_denominator) and len(digits) > len(prefixed_denominator):
        return int(digits[: -len(prefixed_denominator)])
    denominator = str(max_value)
    if digits.endswith(denominator) and len(digits) > len(denominator):
        return int(digits[: -len(denominator)])
    return None


# ── OCR 识别 ────────────────────────────────────────────────────────────────


def recognize_text(
    image: numpy.ndarray,
    *,
    roi: ROI | None = None,
    allowlist: str = '',
    recognition_profile: RecognitionProfile | str = RecognitionProfile.FULL,
    candidates: Sequence[str] | None = None,
) -> list[TextDetection]:
    """执行 ROI 裁切、OCR 识别和候选约束。

    Args:
        image: 待识别的 RGB 图片数组。
        roi: 可选的相对坐标识别区域。
        allowlist: 可选的允许字符集合。
        recognition_profile: 完整文字或单行文字识别模式。
        candidates: 可选的完整结果候选集合。

    Returns:
        按图片阅读顺序排列的标准化识别结果。

    Raises:
        ValueError: 识别模式不是已定义的模式。
    """
    # 1. 先裁切调用方指定的区域，保证 OCR 坐标相对于识别输入。
    source_image = roi.crop(image) if roi is not None else image
    profile = RecognitionProfile(recognition_profile)

    # 2. 根据识别模式选择完整检测或单行识别。
    executor = _ocr_executor()
    detections = (
        executor.recognize_line(source_image, allowlist)
        if profile is RecognitionProfile.SINGLE_LINE
        else executor.recognize(source_image, allowlist)
    )
    _log.debug(
        '[VISION] OCR → 识别结果：profile={!r}, detection_count={}',
        profile.value,
        len(detections),
    )
    if candidates is None:
        return detections

    # 3. 只保留调用方明确允许的完整文本，不在通用层猜测业务结果。
    allowed_texts = set(candidates)
    matched_detections = [
        detection for detection in detections if detection.recognized_text in allowed_texts
    ]
    _log.debug(
        '[VISION] OCR → 候选约束：candidate_count={}, matched_count={}',
        len(candidates),
        len(matched_detections),
    )
    return matched_detections


def recognize_prepared_text(
    image: numpy.ndarray,
    *,
    roi: ROI | None = None,
    allowlist: str = '',
    recognition_profile: RecognitionProfile | str = RecognitionProfile.FULL,
    candidates: Sequence[str] | None = None,
    scale: int = OPENCV_TEXT_SCALE,
    blur_kernel: int = OPENCV_TEXT_BLUR_KERNEL,
) -> list[TextDetection]:
    """执行 ROI 裁切、OpenCV 文本预处理和 OCR 识别。

    Args:
        image: 待识别的 RGB 图片数组。
        roi: 可选的相对坐标识别区域。
        allowlist: 可选的允许字符集合。
        recognition_profile: 完整文字或单行文字识别模式。
        candidates: 可选的完整结果候选集合。
        scale: 文本放大倍数。
        blur_kernel: 高斯模糊核边长，必须为正奇数。

    Returns:
        按图片阅读顺序排列的标准化识别结果。
    """
    # 1. 先确定识别区域，再对区域内文字执行通用预处理。
    source_image = roi.crop(image) if roi is not None else image
    prepared = prepare_text(source_image, scale=scale, blur_kernel=blur_kernel)

    # 2. 预处理结果已经是识别输入，因此不再次传入 ROI。
    return recognize_text(
        prepared,
        allowlist=allowlist,
        recognition_profile=recognition_profile,
        candidates=candidates,
    )


# ── 私有辅助 ────────────────────────────────────────────────────────────────


@cache
def _ocr_executor() -> OCRExecutor:
    """按需创建并复用唯一的 OCR 原子执行器。

    OCRExecutor 构造时要加载识别模型，代价远高于一次识别，必须复用同一个实例。
    """
    return OCRExecutor()


__all__ = [
    'RecognitionProfile',
    'parse_counter',
    'prepare_text',
    'recognize_prepared_text',
    'recognize_text',
]
