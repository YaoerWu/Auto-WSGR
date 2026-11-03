"""模块功能：验证 common.vision 公共入口的截图、重试与识别判定流程。

直接调用方：application、dispatch 等上层通过公共入口确认页面状态。
直接依赖：service 的公共入口、adapters 匹配函数和时间等待。
边界：不初始化 OCR 模型、不读取模板文件，也不触碰真实设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from autowsgr.common.vision import service
from autowsgr.common.vision.adapters.template_matching import ROI
from autowsgr.common.vision.ocr import TextDetection


def _frame(value: int = 0) -> np.ndarray:
    """构造一帧可区分的画面。"""
    return np.full((10, 20, 3), value, dtype=np.uint8)


def _context(*frames: np.ndarray) -> tuple[SimpleNamespace, list[np.ndarray]]:
    """构造按顺序返回画面的假 ContextHandle。"""
    recorded: list[np.ndarray] = []
    pending = iter(frames)
    ctx = SimpleNamespace(
        runtime=SimpleNamespace(ctrl=SimpleNamespace(screenshot=lambda: next(pending))),
        record_screenshot=recorded.append,
    )
    return ctx, recorded


def _match(matched: bool, center: tuple[float, float] | None = None) -> SimpleNamespace:
    """构造模板匹配结果替身。"""
    return SimpleNamespace(matched=matched, center=center)


def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """接管识别间隔等待并返回记录列表。"""
    sleeps: list[float] = []
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)
    return sleeps


def test_screenshot_registers_frame_and_first_hit_returns_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """截图入口登记最新画面；首帧命中即返回，不等待也不重试。"""
    frame = _frame(7)
    ctx, recorded = _context(frame, _frame(1))

    assert service.screenshot(ctx) is frame
    assert recorded == [frame]

    first = _frame(1)
    ctx, recorded = _context(first)
    sleeps = _patch_sleep(monkeypatch)
    calls: list[tuple[bool, object, object, float]] = []
    monkeypatch.setattr(
        service.adapters,
        'match_templates',
        lambda image, template, *, roi, confidence: (
            calls.append((image is first, template, roi, confidence)) or [_match(True)]
        ),
    )

    result = service.expect_template(
        ctx,
        template='tpl',
        roi='area',
        confidence=0.9,
        attempts=3,
        interval_seconds=0.25,
    )

    assert result.satisfied is True
    assert result.screenshot is first
    assert result.observation[0].matched is True
    assert calls == [(True, 'tpl', 'area', 0.9)]
    assert sleeps == []
    assert recorded == [first]


def test_expect_template_retries_then_succeeds_or_exhausts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未满足时等待后重试并返回最新画面，用尽次数则返回最后一次观测。"""
    first, second = _frame(1), _frame(2)
    ctx, recorded = _context(first, second)
    sleeps = _patch_sleep(monkeypatch)
    responses = iter(([_match(False)], [_match(True)]))
    monkeypatch.setattr(service.adapters, 'match_templates', lambda *_, **__: next(responses))

    result = service.expect_template(ctx, template='tpl', attempts=3, interval_seconds=0.25)

    assert result.satisfied is True
    assert result.screenshot is second
    assert recorded == [first, second]
    assert sleeps == [0.25]

    exhausted, _ = _context(_frame(1), _frame(2), _frame(3))
    monkeypatch.setattr(service.adapters, 'match_templates', lambda *_, **__: [_match(False)])
    failed = service.expect_template(exhausted, template='tpl', attempts=3, interval_seconds=0.5)

    assert failed.satisfied is False
    assert failed.observation[0].matched is False
    assert sleeps == [0.25, 0.5, 0.5]


def test_expect_template_verdict_and_parameter_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """absent 翻转结论、命中数量按 min_matches 判定，三个边界参数都显式校验。"""
    _patch_sleep(monkeypatch)
    monkeypatch.setattr(service.adapters, 'match_templates', lambda *_, **__: [_match(False)])
    assert service.expect_template(_context(_frame(1))[0], template='tpl', absent=True).satisfied

    monkeypatch.setattr(service.adapters, 'match_templates', lambda *_, **__: [_match(True)])
    assert not service.expect_template(
        _context(_frame(1), _frame(2))[0], template='tpl', attempts=2, absent=True
    ).satisfied

    monkeypatch.setattr(
        service.adapters,
        'match_templates',
        lambda *_, **__: [_match(True), _match(False), _match(True)],
    )
    assert service.expect_template(_context(_frame(1))[0], template='tpl', min_matches=2).satisfied
    assert not service.expect_template(
        _context(_frame(1))[0], template='tpl', attempts=1, min_matches=3
    ).satisfied

    for kwargs, message in (
        ({'min_matches': 0}, 'min_matches 必须是大于零的整数'),
        ({'min_matches': True}, 'min_matches 必须是大于零的整数'),
        ({'attempts': 0}, 'attempts 必须是大于零的整数'),
        ({'attempts': True}, 'attempts 必须是大于零的整数'),
        ({'interval_seconds': -0.1}, 'interval_seconds 不能小于零'),
        ({'interval_seconds': True}, 'interval_seconds 不能小于零'),
    ):
        with pytest.raises(ValueError, match=message):
            service.expect_template(
                _context(_frame(1))[0],
                template='tpl',
                **kwargs,  # type: ignore[arg-type]
            )


def test_expect_template_center_returns_first_matched_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中心入口取第一个带中心的命中，没有命中或缺少中心时返回 None。"""
    frame = _frame(1)
    monkeypatch.setattr(
        service,
        'expect_template',
        lambda *_, **__: service.RecognitionResult(
            True, [_match(False), _match(True, (0.4, 0.6))], frame
        ),
    )
    assert service.expect_template_center(object(), template='tpl') == (0.4, 0.6)

    monkeypatch.setattr(
        service,
        'expect_template',
        lambda *_, **__: service.RecognitionResult(True, [_match(True, None)], _frame()),
    )
    assert service.expect_template_center(object(), template='tpl') is None


def test_expect_ocr_reads_text_or_asserts_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """省略 expect 只读取；给字符串要求整段相等，给序列命中任一候选即可。"""
    _patch_sleep(monkeypatch)
    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_, **__: [])
    read_only = service.expect_ocr(_context(_frame(1))[0])
    assert read_only.satisfied is True
    assert read_only.observation == []

    detections = [TextDetection('go', 0.9, (0, 0, 10, 10))]
    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_, **__: detections)
    assert service.expect_ocr(_context(_frame(1))[0], expect='go', attempts=1).satisfied is True
    assert service.expect_ocr(_context(_frame(1))[0], expect='stop', attempts=1).satisfied is False

    candidates = [TextDetection('最强之舟（困难）', 0.91, (0, 0, 20, 10))]
    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_, **__: candidates)
    assert service.expect_ocr(
        _context(_frame(1))[0], expect=('最强之舟', '最强之舟（困难）'), attempts=1
    ).satisfied

    monkeypatch.setattr(service.adapters, 'recognize_text', lambda *_, **__: [])
    assert service.expect_ocr(
        _context(_frame(1))[0], expect='go', attempts=1, absent=True
    ).satisfied

    with pytest.raises(ValueError, match='expect 候选集合不能为空'):
        service.expect_ocr(object(), expect=())


def test_expect_ocr_groups_regions_passes_options_and_normalizes_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """roi 传序列时按区域分组观测并透传选项；中心入口按截图尺寸归一化。"""
    _patch_sleep(monkeypatch)
    regions: list[ROI | None] = []
    options: list[dict[str, object]] = []

    def fake_recognize(
        _image: np.ndarray, *, roi: ROI | None, **kwargs: object
    ) -> list[TextDetection]:
        regions.append(roi)
        options.append({'roi': roi, **kwargs})
        text = 'go' if roi is not None and roi.x1 > 0 else 'other'
        return [TextDetection(text, 0.9, (0, 0, 4, 4))]

    monkeypatch.setattr(service.adapters, 'recognize_text', fake_recognize)

    result = service.expect_ocr(
        _context(_frame(1))[0],
        expect='go',
        roi=(ROI(0.0, 0.0, 0.5, 0.5), ROI(0.5, 0.5, 1.0, 1.0)),
        allowlist='go',
        recognition_profile='single_line',
        candidates=('go',),
    )

    assert [region.x1 for region in regions if region is not None] == [0.0, 0.5]
    assert result.satisfied is True
    assert [[detection.recognized_text for detection in group] for group in result.observation] == [
        ['other'],
        ['go'],
    ]
    assert options[0] == {
        'roi': ROI(0.0, 0.0, 0.5, 0.5),
        'allowlist': 'go',
        'recognition_profile': 'single_line',
        'candidates': ('go',),
    }

    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    monkeypatch.setattr(
        service,
        'expect_ocr',
        lambda *_, **__: service.RecognitionResult(
            True, [TextDetection('go', 0.9, (10, 20, 30, 40))], frame
        ),
    )
    assert service.expect_ocr_center(object(), expect='go') == (0.125, 0.4)

    for missing in (
        service.RecognitionResult(False, [TextDetection('go', 0.9, (10, 20, 30, 40))], frame),
        service.RecognitionResult(True, [TextDetection('go', 0.9, None)], frame),
    ):
        monkeypatch.setattr(service, 'expect_ocr', lambda *_args, _r=missing, **_kwargs: _r)
        assert service.expect_ocr_center(object(), expect='go') is None


def test_expect_pixels_counts_hits_and_pixel_center_returns_first_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """像素期望按命中数量判定并支持 absent；中心入口取第一个命中规则。"""
    _patch_sleep(monkeypatch)
    monkeypatch.setattr(
        service.adapters,
        'match_pixels',
        lambda *_, **__: [SimpleNamespace(matched=True), SimpleNamespace(matched=False)],
    )

    assert service.expect_pixels(_context(_frame(1))[0], signature='sig', attempts=1).satisfied
    assert not service.expect_pixels(
        _context(_frame(1))[0], signature='sig', attempts=1, min_matches=2
    ).satisfied
    assert service.expect_pixels(
        _context(_frame(1))[0], signature='sig', attempts=1, min_matches=2, absent=True
    ).satisfied

    with pytest.raises(ValueError, match='min_matches 必须是大于零的整数'):
        service.expect_pixels(object(), signature='sig', min_matches=0)  # type: ignore[arg-type]

    monkeypatch.setattr(
        service,
        'expect_pixels',
        lambda *_, **__: service.RecognitionResult(
            True,
            [
                SimpleNamespace(
                    details=[
                        SimpleNamespace(matched=False, rule=SimpleNamespace(x=0.1, y=0.2)),
                        SimpleNamespace(matched=True, rule=SimpleNamespace(x=0.3, y=0.7)),
                    ]
                )
            ],
            _frame(),
        ),
    )
    assert service.expect_pixel_center(object(), signature='sig') == (0.3, 0.7)

    monkeypatch.setattr(
        service,
        'expect_pixels',
        lambda *_, **__: service.RecognitionResult(False, [], _frame()),
    )
    assert service.expect_pixel_center(object(), signature='sig') is None
