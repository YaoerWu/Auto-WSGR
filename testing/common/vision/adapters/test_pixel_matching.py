"""模块功能：验证像素匹配适配层的规则校验、策略判定与组合签名流程。

直接调用方：common.vision.service 的 expect_pixels / expect_pixel_center。
直接依赖：Color、PixelRule、PixelSignature、CompositePixelSignature、match_pixels。
边界：NumPy 采样由替身接管，不依赖真实截图。
"""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.common.vision.adapters import pixel_matching
from autowsgr.common.vision.adapters.pixel_matching import (
    Color,
    CompositePixelSignature,
    MatchStrategy,
    PixelMatchResult,
    PixelRule,
    PixelSignature,
    match_pixels,
)
from autowsgr.common.vision.adapters.template_matching import ROI


WHITE = Color(10, 20, 30)
RED = Color(200, 0, 0)


def _image(height: int = 20, width: int = 30) -> np.ndarray:
    """构造黑色画面。"""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _patch_samples(monkeypatch: pytest.MonkeyPatch, pixels: object) -> None:
    """让执行器返回固定的采样结果。"""
    monkeypatch.setattr(
        pixel_matching._EXECUTOR,
        'sample_pixels',
        lambda _image, _positions: np.asarray(pixels, dtype=np.uint8),
    )


def test_color_distance_and_pixel_rule_validate_inputs() -> None:
    """颜色距离按欧氏距离计算且含容差边界，规则坐标与容差越界直接报错。"""
    current = Color(10, 20, 30)
    other = Color(13, 24, 30)
    assert current.distance(other) == 5.0
    assert current.near(other, tolerance=5.0) is True
    assert current.near(other, tolerance=4.9) is False
    assert current.as_tuple() == (10, 20, 30)

    for x, y in ((-0.1, 0.5), (1.1, 0.5), (0.5, -0.1), (0.5, 1.1)):
        with pytest.raises(ValueError, match='像素规则坐标必须位于'):
            PixelRule(x, y, WHITE)

    with pytest.raises(ValueError, match='像素规则容差不能为负数'):
        PixelRule(0.5, 0.5, WHITE, tolerance=-1.0)


@pytest.mark.parametrize(
    ('strategy', 'threshold', 'expected'),
    [
        (MatchStrategy.ALL, 0, False),
        (MatchStrategy.ANY, 0, True),
        (MatchStrategy.COUNT, 1, True),
        (MatchStrategy.COUNT, 2, False),
    ],
)
def test_signature_applies_match_strategy(
    monkeypatch: pytest.MonkeyPatch,
    strategy: MatchStrategy,
    threshold: int,
    expected: bool,
) -> None:
    """规则序列固定为元组，ALL、ANY 与 COUNT 分别按全部、任一和阈值判定。"""
    _patch_samples(monkeypatch, [[10, 20, 30], [0, 0, 0]])
    signature = PixelSignature(
        'probe',
        [PixelRule(0.1, 0.1, WHITE), PixelRule(0.2, 0.2, RED)],
        strategy=strategy,
        threshold=threshold,
    )

    assert isinstance(signature.rules, tuple)
    result = match_pixels(_image(), signature)[0]

    assert result.matched is expected
    assert result.matched_count == 1
    assert result.total_count == 2
    assert result.ratio == 0.5
    assert bool(result) is expected


def test_match_pixels_returns_rule_details_on_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    """with_details 为真时逐规则返回实际颜色、距离和命中状态。"""
    _patch_samples(monkeypatch, [[10, 20, 30], [0, 0, 0]])
    signature = PixelSignature(
        'probe',
        (PixelRule(0.1, 0.1, WHITE), PixelRule(0.2, 0.2, RED)),
        strategy=MatchStrategy.ANY,
    )

    without_details = match_pixels(_image(), signature)[0]
    with_details = match_pixels(_image(), signature, with_details=True)[0]

    assert without_details.details == ()
    assert len(with_details.details) == 2
    assert with_details.details[0].actual == WHITE
    assert with_details.details[0].distance == 0.0
    assert with_details.details[0].matched is True
    assert with_details.details[1].actual == Color(0, 0, 0)
    assert with_details.details[1].matched is False

    assert match_pixels(_image(), PixelSignature('all', ()))[0].matched is True
    assert (
        match_pixels(_image(), PixelSignature('any', (), strategy=MatchStrategy.ANY))[0].matched
        is True
    )
    assert (
        match_pixels(
            _image(), PixelSignature('zero', (), strategy=MatchStrategy.COUNT, threshold=0)
        )[0].matched
        is True
    )
    assert (
        match_pixels(
            _image(), PixelSignature('two', (), strategy=MatchStrategy.COUNT, threshold=2)
        )[0].matched
        is False
    )
    assert PixelMatchResult(False, 'probe', 0, 0).ratio == 0.0


def test_composite_signature_returns_first_matching_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合签名按顺序尝试，命中即带出候选名，全部失败时给出未命中与逐规则详情。"""
    _patch_samples(monkeypatch, [[10, 20, 30]])
    missed = PixelSignature('missed', (PixelRule(0.5, 0.5, RED),))
    hit = PixelSignature('hit', (PixelRule(0.5, 0.5, WHITE),))
    composite = CompositePixelSignature('probe', (missed, hit))

    result = match_pixels(_image(), composite)[0]
    assert len(composite) == 2
    assert result.matched is True
    assert result.signature_name == 'probe'
    assert result.matched_signature == 'hit'
    assert result.matched_count == 1
    assert result.total_count == 2

    full_miss = CompositePixelSignature('probe', (missed,))
    miss_result = match_pixels(_image(), full_miss, with_details=True)[0]
    assert miss_result.matched is False
    assert miss_result.matched_signature is None
    assert miss_result.matched_count == 0
    assert len(miss_result.details) == 1


def test_match_pixels_crops_the_image_before_sampling(monkeypatch: pytest.MonkeyPatch) -> None:
    """传入 ROI 时先裁切再采样，多签名时可各自限定区域。"""
    shapes: list[tuple[int, ...]] = []

    def fake_sample(image: np.ndarray, _positions: object) -> np.ndarray:
        shapes.append(image.shape)
        return np.asarray([[10, 20, 30]], dtype=np.uint8)

    monkeypatch.setattr(pixel_matching._EXECUTOR, 'sample_pixels', fake_sample)
    signature = PixelSignature('probe', (PixelRule(0.5, 0.5, WHITE),))
    match_pixels(_image(20, 40), signature, roi=ROI(0.5, 0.5, 1.0, 1.0))
    match_pixels(_image(20, 40), (signature, signature), roi=(ROI(0.5, 0.5, 1.0, 1.0), None))

    assert shapes == [(10, 20, 3), (10, 20, 3), (20, 40, 3)]


def test_match_pixels_validates_arguments() -> None:
    """签名与区域参数按单签名/签名序列分别校验，长度不一致或类型错误都拒绝。"""
    signature = PixelSignature('probe', (PixelRule(0.5, 0.5, WHITE),))

    with pytest.raises(ValueError, match='签名序列不能为空'):
        match_pixels(_image(), ())

    with pytest.raises(
        TypeError, match='签名序列中的元素必须是 PixelSignature 或 CompositePixelSignature'
    ):
        match_pixels(_image(), ('probe',))  # type: ignore[arg-type]

    for invalid in (42, 'probe', b'probe'):
        with pytest.raises(
            TypeError, match='signature 必须是 PixelSignature、CompositePixelSignature 或签名序列'
        ):
            match_pixels(_image(), invalid)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match='roi 序列长度必须与签名数量一致'):
        match_pixels(_image(), (signature, signature), roi=(ROI(0, 0, 1, 1),))

    with pytest.raises(TypeError, match='roi 序列中的元素必须是 ROI 或 None'):
        match_pixels(_image(), (signature, signature), roi=(ROI(0, 0, 1, 1), 'area'))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match='roi 必须是 ROI、ROI 序列或 None'):
        match_pixels(_image(), (signature, signature), roi=42)  # type: ignore[arg-type]
