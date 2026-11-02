"""模块功能：验证 common.vision 的公共入口和通用组合流程。

直接调用方：项目测试运行器。

直接依赖：NumPy、pytest 和 common.vision 公共能力。

边界：不初始化真实设备，不加载 MaaFramework OCR 模型，不验证上层业务识别规则。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from autowsgr.common import vision
from autowsgr.common.vision import service
from autowsgr.common.vision.adapters import match_pixels, match_template, text_recognition
from autowsgr.common.vision.adapters.pixel_matching import (
    Color,
    CompositePixelSignature,
    PixelRule,
    PixelSignature,
)
from autowsgr.common.vision.adapters.template_matching import ROI, Template
from autowsgr.common.vision.ocr import TextDetection


if TYPE_CHECKING:
    from collections.abc import Callable


def test_public_service_exports_are_stable() -> None:
    """公共入口只暴露识别功能与识别数据模型。"""
    entries = (
        'screenshot',
        'expect_template',
        'expect_ocr',
        'expect_pixels',
        'expect_template_center',
        'expect_ocr_center',
        'expect_pixel_center',
    )
    for entry in entries:
        assert callable(getattr(vision, entry))
    assert vision.ROI is ROI
    assert vision.Template is Template
    assert vision.RecognitionResult is service.RecognitionResult


def test_pixel_matching_composes_roi_sampling_and_rule_evaluation() -> None:
    """像素匹配可以在 ROI 内采样并返回规则结果。"""
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[10, 15] = (10, 20, 30)
    signature = PixelSignature(
        name='pixel',
        rules=(PixelRule(0.5, 0.5, Color(10, 20, 30)),),
    )

    results = match_pixels(image, signature, roi=ROI(0.0, 0.0, 1.0, 1.0))

    assert len(results) == 1
    assert results[0].matched
    assert results[0].matched_signature == 'pixel'
    assert results[0].ratio == 1.0


def test_pixel_matching_evaluates_multiple_signatures_in_one_call() -> None:
    """一次调用可判定多组签名，组合签名带出命中的候选名。"""
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    image[10, 15] = (10, 20, 30)
    expected = PixelSignature('normal', (PixelRule(0.5, 0.5, Color(10, 20, 30)),))
    alternative = PixelSignature('severe', (PixelRule(0.5, 0.5, Color(200, 0, 0)),))
    composite = CompositePixelSignature('probe', (alternative, expected))

    results = match_pixels(image, (composite, composite, expected))

    assert [result.matched_signature for result in results] == ['normal', 'normal', 'normal']
    assert results[0].signature_name == 'probe'
    assert results[0].matched_count == 1
    assert results[0].total_count == 2


def test_pixel_matching_reports_no_candidate_when_nothing_matches() -> None:
    """组合签名全部不命中时结果为假，候选名为空。"""
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    alternative = PixelSignature('severe', (PixelRule(0.5, 0.5, Color(200, 0, 0)),))
    composite = CompositePixelSignature('probe', (alternative,))

    result = match_pixels(image, composite)[0]

    assert result.matched is False
    assert result.matched_signature is None
    assert result.matched_count == 0


def test_pixel_matching_requires_matching_roi_count() -> None:
    """roi 传序列时必须与签名数量一致。"""
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    signature = PixelSignature('pixel', (PixelRule(0.5, 0.5, Color(0, 0, 0)),))

    with pytest.raises(ValueError, match='roi 序列长度必须与签名数量一致'):
        match_pixels(image, (signature, signature), roi=(ROI(0.0, 0.0, 1.0, 1.0),))


def test_template_matching_returns_absolute_location_from_roi() -> None:
    """模板匹配应把 ROI 内位置还原为原图像素坐标。"""
    template_image = np.arange(10 * 12 * 3, dtype=np.uint8).reshape((10, 12, 3))
    image = np.full((60, 80, 3), 17, dtype=np.uint8)
    image[20:30, 30:42] = template_image
    template = Template(
        name='sample',
        relative_path='sample.png',
        image=template_image,
        source_resolution=(80, 60),
    )

    result = match_template(
        image,
        template,
        roi=ROI(0.25, 0.25, 0.8, 0.9),
        confidence=0.99,
    )

    assert result.matched
    assert result.location == (30, 20)
    assert result.template_path == 'sample.png'


def test_text_preparation_and_counter_parser() -> None:
    """文本预处理保持 RGB 输出，计数解析覆盖分隔符和丢失分隔符。"""
    image = np.zeros((5, 7, 3), dtype=np.uint8)

    prepared = text_recognition.prepare_text(image)

    assert prepared.shape == (20, 28, 3)
    assert text_recognition.parse_counter('3/10', 10) == 3
    assert text_recognition.parse_counter('310', 10) == 3
    with pytest.raises(ValueError, match='文本中无数字'):
        text_recognition.parse_counter('none', 10)


def test_ocr_entry_uses_profile_and_candidate_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR 组合方法应选择识别模式并应用候选约束。"""

    class FakeOCRExecutor:
        def recognize_line(
            self,
            image: np.ndarray,
            allowlist: str,
        ) -> list[TextDetection]:
            assert image.shape == (10, 12, 3)
            assert allowlist == '0123456789'
            return [TextDetection('123', 0.95, (0, 0, 12, 10))]

        def recognize(
            self,
            _image: np.ndarray,
            _allowlist: str,
        ) -> list[TextDetection]:
            raise AssertionError('单行识别配置不应调用完整识别入口')

    monkeypatch.setattr(text_recognition, '_ocr_executor', FakeOCRExecutor)

    result = text_recognition.recognize_text(
        np.zeros((10, 12, 3), dtype=np.uint8),
        allowlist='0123456789',
        recognition_profile='single_line',
        candidates=('123',),
    )

    assert result == [TextDetection('123', 0.95, (0, 0, 12, 10))]


def test_ocr_expect_accepts_candidate_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR 期望支持候选集合：命中任一即算找到。"""
    detections = [TextDetection('最强之舟（困难）', 0.91, (0, 0, 20, 10))]
    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_args, **_kwargs: detections)
    monkeypatch.setattr(
        service,
        '_retry',
        lambda _ctx, *, observe, accept, **_kwargs: service.RecognitionResult(
            accept(observe(None)), detections, None
        ),
    )

    assert service.expect_ocr(object(), expect='最强之舟（困难）').satisfied is True
    assert service.expect_ocr(object(), expect=('最强之舟', '最强之舟（困难）')).satisfied is True
    assert service.expect_ocr(object(), expect=('最强之舟',)).satisfied is False


def _stub_pixel_retry(
    monkeypatch: pytest.MonkeyPatch,
    *,
    matched_flags: tuple[bool, ...],
    frames: list[object],
) -> None:
    """用替身接管像素匹配和重试循环，让一次调用就完成判定。"""
    sentinel = object()

    def fake_match(frame: object, *_args: object, **_kwargs: object) -> list[SimpleNamespace]:
        frames.append(frame)
        return [SimpleNamespace(matched=flag) for flag in matched_flags]

    def fake_retry(
        _ctx: object,
        *,
        observe: Callable[[object], object],
        accept: Callable[[object], bool],
        **_kwargs: object,
    ) -> service.RecognitionResult[object]:
        observation = observe(sentinel)
        return service.RecognitionResult(accept(observation), observation, sentinel)

    monkeypatch.setattr(service.adapters, 'match_pixels', fake_match)
    monkeypatch.setattr(service, '_retry', fake_retry)


def test_pixel_expect_evaluates_all_signatures_in_one_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """像素期望在同一帧上判定全部签名，观测按签名顺序返回。"""
    frames: list[object] = []
    _stub_pixel_retry(monkeypatch, matched_flags=(True, False), frames=frames)

    result = service.expect_pixels(object(), signature=(object(), object()))

    assert len(frames) == 1
    assert result.satisfied is True
    assert [match.matched for match in result.observation] == [True, False]


def test_pixel_expect_min_matches_controls_the_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """命中数量低于 min_matches 才算不满足，absent 再翻转一次。"""
    frames: list[object] = []
    _stub_pixel_retry(monkeypatch, matched_flags=(True, False), frames=frames)

    assert service.expect_pixels(object(), signature=(object(), object())).satisfied is True
    assert (
        service.expect_pixels(object(), signature=(object(), object()), min_matches=2).satisfied
        is False
    )
    assert (
        service.expect_pixels(
            object(),
            signature=(object(), object()),
            min_matches=2,
            absent=True,
        ).satisfied
        is True
    )


def test_pixel_expect_rejects_invalid_min_matches() -> None:
    """min_matches 必须是大于零的整数。"""
    with pytest.raises(ValueError, match='min_matches 必须是大于零的整数'):
        service.expect_pixels(object(), signature=object(), min_matches=0)


def test_ocr_expect_rejects_empty_candidate_collection() -> None:
    """空候选集合属于非法期望，必须显式失败。"""
    with pytest.raises(ValueError, match='候选集合不能为空'):
        service.expect_ocr(object(), expect=())


def test_ocr_expect_reads_multiple_regions_in_one_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """roi 传序列时应在同一帧上逐个区域识别，观测按区域分组返回。"""
    sentinel = object()
    frames: list[object] = []

    def fake_recognize(frame: object, **_kwargs: object) -> list[TextDetection]:
        frames.append(frame)
        return [TextDetection(f'text-{len(frames)}', 0.9, (0, 0, 5, 5))]

    def fake_retry(
        _ctx: object,
        *,
        observe: Callable[[object], object],
        accept: Callable[[object], bool],
        **_kwargs: object,
    ) -> service.RecognitionResult[object]:
        observation = observe(sentinel)
        return service.RecognitionResult(accept(observation), observation, sentinel)

    monkeypatch.setattr(service.adapters, 'recognize_text', fake_recognize)
    monkeypatch.setattr(service, '_retry', fake_retry)

    result = service.expect_ocr(
        object(),
        roi=(ROI(0.0, 0.0, 0.5, 0.5), ROI(0.5, 0.5, 1.0, 1.0)),
    )

    assert frames == [sentinel, sentinel]
    assert result.satisfied is True
    assert [group[0].recognized_text for group in result.observation] == ['text-1', 'text-2']


def test_ocr_expect_without_expect_only_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """省略 expect 时只读取文本，不做断言。"""
    sentinel = object()

    def fake_retry(
        _ctx: object,
        *,
        observe: Callable[[object], object],
        accept: Callable[[object], bool],
        **_kwargs: object,
    ) -> service.RecognitionResult[object]:
        observation = observe(sentinel)
        return service.RecognitionResult(accept(observation), observation, sentinel)

    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, '_retry', fake_retry)

    result = service.expect_ocr(object(), roi=ROI(0.0, 0.0, 1.0, 1.0))

    assert result.satisfied is True
    assert result.observation == []
