"""模块功能：提供 common.vision 的公共识别能力。

上层调用：
- application、business、dispatch 和 server：确认当前状态或操作结果。

下层依赖：
- common.vision.adapters：提供模板匹配、OCR 和像素匹配的重新修饰方法。
- common.vision.config：提供识别重试参数和模板匹配置信度。
- dispatch.context：提供设备服务和截图事实写入（仅类型注解使用）。

边界：只提供截图、模板识别、OCR 识别、像素识别与三类中心识别；识别数据、规则和预期由调用方
提供，service 不决定识别什么、不执行点击、不解析页面语义。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import adapters, config


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import numpy

    from autowsgr.common.vision.adapters.pixel_matching import (
        CompositePixelSignature,
        PixelMatchResult,
        PixelSignature,
    )
    from autowsgr.common.vision.adapters.template_matching import (
        ROI,
        Template,
        TemplateMatchResult,
    )
    from autowsgr.common.vision.ocr import TextDetection
    from autowsgr.dispatch.context import ContextHandle


_log = get_logger('vision.recognition')


# ── 识别结果 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RecognitionResult[T]:
    """一次识别请求的结果。

    Attributes:
        satisfied: 识别结果是否满足调用方给出的预期。
        observation: 本次识别的观测值，类型随识别类型而定。
        screenshot: 做出本次判定所使用的画面。
    """

    satisfied: bool
    observation: T
    screenshot: numpy.ndarray


# ── 公共识别入口 ────────────────────────────────────────────────────────────


def screenshot(ctx: ContextHandle) -> numpy.ndarray:
    """截取当前画面并把这一帧登记为任务上下文的最新截图。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。

    Returns:
        当前设备截图。
    """
    # 先取画面再登记，保证上下文中的最新截图就是本次判定使用的画面。
    frame = ctx.runtime.ctrl.screenshot()
    ctx.record_screenshot(frame)
    return frame


def expect_template(
    ctx: ContextHandle,
    *,
    template: Template | Sequence[Template],
    roi: ROI | Sequence[ROI | None] | None = None,
    confidence: float = config.OPENCV_TEMPLATE_CONFIDENCE,
    min_matches: int = 1,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[TemplateMatchResult]]:
    """重试模板匹配，直到命中数量满足调用方预期。

    absent 决定断言方向：默认期望目标出现，为真时期望目标消失；两种模式共用同一套
    截图与重试循环，只是最后的断言相反。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。
        template: 单个模板，或需要逐个匹配的一组模板。
        roi: 共享搜索区域，或与模板一一对应的区域序列。
        confidence: 期望的匹配置信度，模板分数达到它才算命中。
        min_matches: 期望命中的模板数量。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。
        absent: 期望目标消失时为真，此时命中数量低于 min_matches 才算满足。

    Returns:
        satisfied 表示断言是否满足；observation 是最后一次匹配结果列表。
    """
    if isinstance(min_matches, bool) or not isinstance(min_matches, int) or min_matches < 1:
        raise ValueError('min_matches 必须是大于零的整数')
    return _retry(
        ctx,
        task='模板识别',
        observe=lambda frame: adapters.match_templates(
            frame,
            template,
            roi=roi,
            confidence=confidence,
        ),
        accept=lambda matches: (
            (sum(1 for match in matches if match.matched) >= min_matches) != absent
        ),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )


def expect_template_center(
    ctx: ContextHandle,
    *,
    template: Template | Sequence[Template],
    roi: ROI | Sequence[ROI | None] | None = None,
    confidence: float = config.OPENCV_TEMPLATE_CONFIDENCE,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
) -> tuple[float, float] | None:
    """前识别：重试模板匹配并返回第一个命中模板的中心。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。
        template: 单个模板，或需要逐个匹配的一组模板。
        roi: 共享搜索区域，或与模板一一对应的区域序列。
        confidence: 期望的匹配置信度，模板分数达到它才算命中。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        第一个命中模板的归一化中心；没有命中时为 None。
    """
    template_result = expect_template(
        ctx,
        template=template,
        roi=roi,
        confidence=confidence,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    for match in template_result.observation:
        if match.matched and match.center is not None:
            return match.center
    return None


def expect_ocr(
    ctx: ContextHandle,
    *,
    expect: str | Sequence[str] | None = None,
    roi: ROI | Sequence[ROI | None] | None = None,
    allowlist: str = '',
    recognition_profile: str = 'full',
    candidates: Sequence[str] | None = None,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[TextDetection] | list[list[TextDetection]]]:
    """重试 OCR，直到实际文本满足调用方预期。

    OCR 实际文本与 expect 直接相等比对；模糊匹配、去噪和纠错属于调用方的后处理规则。
    absent 决定断言方向：默认期望文本出现，为真时期望文本消失。

    expect 省略时只读取文本、不做断言；roi 传序列时同一帧内逐个区域识别，observation
    按区域分组返回，与 roi 顺序一致。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。
        expect: 期望识别到的完整文本，或候选集合；候选集合命中任一即算符合预期。
            省略时只读取文本，不做断言。
        roi: OCR 识别区域，或需要逐个识别的一组区域。
        allowlist: 允许识别的字符集合。
        recognition_profile: OCR 识别配置名称。
        candidates: OCR 完整文本候选集合。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。
        absent: 期望文本消失时为真，此时文本不再命中才算满足。

    Returns:
        satisfied 表示断言是否满足；observation 是最后一次 OCR 结果。roi 为序列时每个
        区域一组，单区域时是检测列表。
    """
    expected: tuple[str, ...] | None = None
    if expect is not None:
        expected = (expect,) if isinstance(expect, str) else tuple(expect)
        if not expected:
            raise ValueError('expect 候选集合不能为空')
    if isinstance(roi, (list, tuple)):
        return _retry(
            ctx,
            task='OCR 识别',
            observe=lambda frame: [
                adapters.recognize_text(
                    frame,
                    roi=region,
                    allowlist=allowlist,
                    recognition_profile=recognition_profile,
                    candidates=candidates,
                )
                for region in roi
            ],
            accept=lambda groups: _is_text_matched(groups, expected, absent),
            attempts=attempts,
            interval_seconds=interval_seconds,
        )
    return _retry(
        ctx,
        task='OCR 识别',
        observe=lambda frame: adapters.recognize_text(
            frame,
            roi=roi,
            allowlist=allowlist,
            recognition_profile=recognition_profile,
            candidates=candidates,
        ),
        accept=lambda detections: _is_text_matched((detections,), expected, absent),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )


def expect_pixels(
    ctx: ContextHandle,
    *,
    signature: (
        PixelSignature
        | CompositePixelSignature
        | Sequence[PixelSignature | CompositePixelSignature]
    ),
    roi: ROI | Sequence[ROI | None] | None = None,
    with_details: bool = False,
    min_matches: int = 1,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
    absent: bool = False,
) -> RecognitionResult[list[PixelMatchResult]]:
    """重试像素匹配，直到命中数量满足调用方预期。

    一次调用只截一帧，同一帧内可以并行判定多组签名：一组签名对应一个探针位
    （或多个探针位的组合），每个探针位用 CompositePixelSignature 表达「命中
    任一候选即成立」，命中的候选名由结果的 matched_signature 带出。这样「N 选
    一归类」和「多点组合断言」都由一次调用完成。

    absent 决定断言方向：默认期望命中数量达标，为真时期望命中数量不达标。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。
        signature: 单个像素签名、签名组合，或需要逐个判定的一组签名。
        roi: 共享采样区域，或与签名一一对应的区域序列。
        with_details: 是否要求结果包含逐规则详情。
        min_matches: 期望命中的签名数量。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。
        absent: 期望命中数量低于 min_matches 时为真。

    Returns:
        satisfied 表示断言是否满足；observation 是按签名顺序排列的最后一次匹配结果。
    """
    if isinstance(min_matches, bool) or not isinstance(min_matches, int) or min_matches < 1:
        raise ValueError('min_matches 必须是大于零的整数')
    return _retry(
        ctx,
        task='像素识别',
        observe=lambda frame: adapters.match_pixels(
            frame,
            signature,
            roi=roi,
            with_details=with_details,
        ),
        accept=lambda matches: (
            (sum(1 for match in matches if match.matched) >= min_matches) != absent
        ),
        attempts=attempts,
        interval_seconds=interval_seconds,
    )


# ── 识别重试和判定 ──────────────────────────────────────────────────────────


def expect_ocr_center(
    ctx: ContextHandle,
    *,
    expect: str | Sequence[str],
    roi: ROI | None = None,
    allowlist: str = '',
    recognition_profile: str = 'full',
    candidates: Sequence[str] | None = None,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
) -> tuple[float, float] | None:
    """读取期望文本命中区域的归一化中心，供点击使用。"""
    result = expect_ocr(
        ctx,
        expect=expect,
        roi=roi,
        allowlist=allowlist,
        recognition_profile=recognition_profile,
        candidates=candidates,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if not result.satisfied or result.screenshot is None:
        return None
    expected = (expect,) if isinstance(expect, str) else tuple(expect)
    height, width = result.screenshot.shape[:2]
    for detection in result.observation:
        region = detection.text_region
        if detection.recognized_text in expected and region is not None:
            left, top, region_width, region_height = region
            return (
                (left + region_width / 2) / width,
                (top + region_height / 2) / height,
            )
    return None


def expect_pixel_center(
    ctx: ContextHandle,
    *,
    signature: (
        PixelSignature
        | CompositePixelSignature
        | Sequence[PixelSignature | CompositePixelSignature]
    ),
    roi: ROI | Sequence[ROI | None] | None = None,
    attempts: int = config.DEFAULT_RECOGNITION_ATTEMPTS,
    interval_seconds: float = config.DEFAULT_RECOGNITION_INTERVAL_SECONDS,
) -> tuple[float, float] | None:
    """读取像素签名中第一个命中规则的归一化位置，供点击使用。"""
    result = expect_pixels(
        ctx,
        signature=signature,
        roi=roi,
        with_details=True,
        attempts=attempts,
        interval_seconds=interval_seconds,
    )
    if not result.satisfied:
        return None
    for match in result.observation:
        for detail in match.details:
            if detail.matched:
                return (detail.rule.x, detail.rule.y)
    return None


# ── 内部实现 ────────────────────────────────────────────────────────────────


def _retry[T](
    ctx: ContextHandle,
    *,
    task: str,
    observe: Callable[[numpy.ndarray], T],
    accept: Callable[[T], bool],
    attempts: int,
    interval_seconds: float,
) -> RecognitionResult[T]:
    """按调用方预期重试「截图 → 识别 → 判定预期」。

    Args:
        ctx: 提供设备服务和截图事实写入的统一 ContextHandle。
        task: 日志中标识本次识别任务的业务名称。
        observe: 用一帧画面执行一次识别。
        accept: 判断识别结果是否满足调用方给出的预期。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        最近一次识别的结果；satisfied 表示是否满足预期。
    """
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise ValueError('attempts 必须是大于零的整数')
    if isinstance(interval_seconds, bool) or interval_seconds < 0:
        raise ValueError('interval_seconds 不能小于零')
    for attempt in range(1, attempts + 1):
        # 1. 取当前画面并在识别前登记，保证记录与判定使用同一帧。
        frame = screenshot(ctx)
        # 2. 按调用方预期判定本次识别，满足即返回。
        observation = observe(frame)
        if accept(observation):
            # 一次就过是常态，不记；只有等过重试才留一行。
            if attempt > 1:
                _log.debug(
                    '[VISION] 识别流程 → 重试后满足：task={!r}，attempt={}，result={!r}',
                    task,
                    attempt,
                    'satisfied',
                )
            return RecognitionResult(True, observation, frame)
        # 3. 未满足且仍有剩余次数时等待后重试，最终结果交给调用方处理。
        if attempt < attempts:
            time.sleep(interval_seconds)
    _log.debug(
        '[VISION] 识别流程 → 确认结果：task={!r}，max_attempts={}，result={!r}',
        task,
        attempts,
        'not_satisfied',
    )
    return RecognitionResult(False, observation, frame)


def _is_text_matched(
    groups: Sequence[Sequence[TextDetection]],
    expected: tuple[str, ...] | None,
    absent: bool,
) -> bool:
    """判断按区域分组的 OCR 结果是否满足调用方预期。

    Args:
        groups: 每个区域一组检测结果。
        expected: 期望文本元组；为 None 时不做断言。
        absent: 期望文本消失时为真。

    Returns:
        满足预期时为真；未给出期望时恒为真。
    """
    if expected is None:
        return True
    matched = any(detection.recognized_text in expected for group in groups for detection in group)
    return matched != absent


__all__ = [
    'RecognitionResult',
    'expect_ocr',
    'expect_ocr_center',
    'expect_pixel_center',
    'expect_pixels',
    'expect_template',
    'expect_template_center',
    'screenshot',
]
