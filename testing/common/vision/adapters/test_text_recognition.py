"""模块功能：验证 OCR 适配层的文本预处理、计数解析与识别流程。

直接调用方：common.vision.service 的 expect_ocr / expect_ocr_center。
直接依赖：prepare_text、parse_counter、recognize_text、recognize_prepared_text。
边界：OpenCV 与 FastOCR 执行器均由替身接管，不加载真实模型。
"""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.common.vision.adapters import text_recognition
from autowsgr.common.vision.adapters.template_matching import ROI
from autowsgr.common.vision.ocr import TextDetection


class _RecordingExecutor:
    """记录调用参数的 OCR 执行器替身。"""

    def __init__(self, detections: list[TextDetection]) -> None:
        self.calls: list[tuple[str, tuple[int, ...], str]] = []
        self._detections = detections

    def recognize(self, image: np.ndarray, allowlist: str) -> list[TextDetection]:
        self.calls.append(('full', image.shape, allowlist))
        return self._detections

    def recognize_line(self, image: np.ndarray, allowlist: str) -> list[TextDetection]:
        self.calls.append(('single_line', image.shape, allowlist))
        return self._detections


def _patch_executor(monkeypatch: pytest.MonkeyPatch, executor: _RecordingExecutor) -> None:
    """把模块级 OCR 执行器工厂换成固定替身。"""
    monkeypatch.setattr(text_recognition, '_ocr_executor', lambda: executor)


def test_prepare_text_runs_the_documented_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """空图片原样返回；非空图片依次执行灰度、放大、模糊、归一化、二值化和转 RGB。"""
    empty = np.empty((0, 0, 3), dtype=np.uint8)
    assert text_recognition.prepare_text(empty) is empty

    calls: list[tuple[object, ...]] = []
    gray = np.zeros((5, 7), dtype=np.uint8)
    scaled = np.zeros((20, 28), dtype=np.uint8)
    normalized = np.zeros((20, 28), dtype=np.uint8)
    binary = np.zeros((20, 28), dtype=np.uint8)
    rgb = np.zeros((20, 28, 3), dtype=np.uint8)

    monkeypatch.setattr(
        text_recognition._OPENCV, 'to_gray', lambda _image: calls.append(('gray',)) or gray
    )
    monkeypatch.setattr(
        text_recognition._OPENCV,
        'resize',
        lambda _image, width, height, *, interpolation: (
            calls.append(('resize', width, height, interpolation)) or scaled
        ),
    )
    monkeypatch.setattr(
        text_recognition._OPENCV,
        'blur',
        lambda _image, kernel: calls.append(('blur', kernel)) or scaled,
    )
    monkeypatch.setattr(
        text_recognition._OPENCV,
        'normalize',
        lambda _image: calls.append(('normalize',)) or normalized,
    )
    monkeypatch.setattr(
        text_recognition._OPENCV,
        'threshold',
        lambda _image: calls.append(('threshold',)) or binary,
    )
    monkeypatch.setattr(
        text_recognition._OPENCV,
        'gray_to_rgb',
        lambda _image: calls.append(('rgb',)) or rgb,
    )

    prepared = text_recognition.prepare_text(
        np.zeros((5, 7, 3), dtype=np.uint8), scale=4, blur_kernel=3
    )

    assert prepared is rgb
    assert calls == [
        ('gray',),
        ('resize', 28, 20, 'cubic'),
        ('blur', 3),
        ('normalize',),
        ('threshold',),
        ('rgb',),
    ]


@pytest.mark.parametrize(
    ('text', 'max_value', 'expected'),
    [
        ('3/10', 10, 3),
        ('12|99', 99, 12),
        ('310', 10, 3),
        ('110', 10, 1),
        ('999', 10, None),
    ],
)
def test_parse_counter_extracts_the_numerator(
    text: str, max_value: int, expected: int | None
) -> None:
    """优先按分隔符取分子，丢失分隔符时按末尾分母拆分。"""
    assert text_recognition.parse_counter(text, max_value) == expected


@pytest.mark.parametrize(
    ('text', 'message'),
    [('abc/10', '分子部分无数字'), ('none', '文本中无数字')],
)
def test_parse_counter_rejects_text_without_a_numerator(text: str, message: str) -> None:
    """没有可用数字时显式失败。"""
    with pytest.raises(ValueError, match=message):
        text_recognition.parse_counter(text, 10)


def test_recognize_text_selects_profile_and_passes_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认走完整检测，single_line 走单行入口，识别前按 ROI 裁切并透传允许字符。"""
    executor = _RecordingExecutor([TextDetection('go', 0.9, (0, 0, 10, 10))])
    _patch_executor(monkeypatch, executor)

    detections = text_recognition.recognize_text(
        np.zeros((10, 12, 3), dtype=np.uint8),
        allowlist='go',
    )
    assert [detection.recognized_text for detection in detections] == ['go']
    assert executor.calls == [('full', (10, 12, 3), 'go')]

    executor.calls.clear()
    text_recognition.recognize_text(
        np.zeros((10, 12, 3), dtype=np.uint8),
        recognition_profile='single_line',
    )
    assert executor.calls == [('single_line', (10, 12, 3), '')]

    executor.calls.clear()
    text_recognition.recognize_text(
        np.zeros((20, 40, 3), dtype=np.uint8),
        roi=ROI(0.5, 0.5, 1.0, 1.0),
    )
    assert executor.calls == [('full', (10, 20, 3), '')]

    with pytest.raises(ValueError, match='unknown'):
        text_recognition.recognize_text(
            np.zeros((10, 12, 3), dtype=np.uint8),
            recognition_profile='unknown',
        )


def test_recognize_text_filters_by_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """候选集合只保留完整文本命中的结果。"""
    detections = [
        TextDetection('最强之舟', 0.9, (0, 0, 10, 10)),
        TextDetection('简单', 0.8, (0, 10, 10, 10)),
    ]
    _patch_executor(monkeypatch, _RecordingExecutor(detections))

    result = text_recognition.recognize_text(
        np.zeros((10, 12, 3), dtype=np.uint8),
        candidates=('最强之舟',),
    )

    assert result == [detections[0]]


def test_recognize_prepared_text_crops_then_prepares_without_a_second_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预处理入口先裁切再预处理，识别时不再重复传入 ROI。"""
    calls: list[tuple[object, ...]] = []
    prepared = np.zeros((4, 8, 3), dtype=np.uint8)
    monkeypatch.setattr(
        text_recognition,
        'prepare_text',
        lambda image, *, scale, blur_kernel: (
            calls.append(('prepare', image.shape, scale, blur_kernel)) or prepared
        ),
    )
    monkeypatch.setattr(
        text_recognition,
        'recognize_text',
        lambda image, **kwargs: calls.append(('recognize', image.shape, kwargs)) or [],
    )

    text_recognition.recognize_prepared_text(
        np.zeros((20, 40, 3), dtype=np.uint8),
        roi=ROI(0.0, 0.0, 0.5, 0.5),
        allowlist='1',
        recognition_profile='single_line',
        candidates=('1',),
        scale=2,
        blur_kernel=5,
    )

    assert calls == [
        ('prepare', (10, 20, 3), 2, 5),
        (
            'recognize',
            (4, 8, 3),
            {
                'allowlist': '1',
                'recognition_profile': 'single_line',
                'candidates': ('1',),
            },
        ),
    ]
