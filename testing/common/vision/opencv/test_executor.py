"""验证 OpenCV 执行器的图片读取、变换与模板匹配流程。

直接调用方：adapters.template_matching 与 adapters.text_recognition 通过这些
算子完成模板加载、缩放和文字预处理。

直接依赖：OpenCV、common.system.files 与 common.vision.config。

边界：只验证算子封装与参数校验，不读取真实模板资源。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from autowsgr.common.vision.config import OPENCV_TEMPLATE_ROOT
from autowsgr.common.vision.opencv import executor as opencv_executor
from autowsgr.common.vision.opencv.executor import OpenCVExecutor


def _rgb(value: int = 120) -> np.ndarray:
    """构造纯色三通道图片。"""
    return np.full((8, 10, 3), value, dtype=np.uint8)


def test_load_image_resolves_under_the_template_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """图片加载固定使用模板根目录并限制读取范围。"""
    calls: list[tuple[object, object]] = []
    sentinel = object()

    def fake_load_image(path: object, *, allowed_root: object) -> object:
        calls.append((path, allowed_root))
        return sentinel

    monkeypatch.setattr(opencv_executor.files, 'load_image', fake_load_image)

    result = OpenCVExecutor.load_image(Path('home') / 'main.png')

    assert result is sentinel
    assert calls == [(OPENCV_TEMPLATE_ROOT / 'home' / 'main.png', OPENCV_TEMPLATE_ROOT)]


def test_gray_and_resize_pipeline() -> None:
    """灰度图原样返回、三通道图转灰度，缩放按 (高度, 宽度) 输出并校验参数。"""
    gray = np.arange(12, dtype=np.uint8).reshape(3, 4)
    assert OpenCVExecutor.to_gray(gray) is gray

    red = np.zeros((2, 2, 3), dtype=np.uint8)
    red[:, :, 0] = 255
    converted = OpenCVExecutor.to_gray(red)
    assert converted.shape == (2, 2)
    assert converted.dtype == np.uint8
    assert all(abs(int(value) - 76) <= 1 for value in converted.ravel())

    for width, height, expected in ((2, 3, (3, 2)), (7, 1, (1, 7))):
        assert OpenCVExecutor.resize(_rgb(), width, height).shape == (*expected, 3)

    for width, height in ((0, 3), (3, 0), (-1, 3)):
        with pytest.raises(ValueError, match='目标图片尺寸必须为正数'):
            OpenCVExecutor.resize(_rgb(), width, height)

    with pytest.raises(ValueError, match='不支持的插值方式'):
        OpenCVExecutor.resize(_rgb(), 2, 2, interpolation='bicubic')


def test_blur_normalize_and_threshold_pipeline() -> None:
    """高斯核必须是正奇数，归一化拉伸到 0-255，Otsu 阈值只输出黑白。"""
    assert OpenCVExecutor.blur(_rgb(), 3).shape == (8, 10, 3)

    for kernel in (2, 0):
        with pytest.raises(ValueError, match='高斯核尺寸必须是正奇数'):
            OpenCVExecutor.blur(_rgb(), kernel)

    normalized = OpenCVExecutor.normalize(np.arange(10, 20, dtype=np.uint8).reshape(2, 5))
    assert int(normalized.min()) == 0
    assert int(normalized.max()) == 255

    binary = OpenCVExecutor.threshold(np.linspace(0, 255, 20, dtype=np.uint8).reshape(4, 5))
    assert set(np.unique(binary).tolist()) <= {0, 255}


def test_gray_to_rgb_expands_channels() -> None:
    """灰度图扩为三通道且各通道一致。"""
    gray = np.arange(6, dtype=np.uint8).reshape(2, 3)

    rgb = OpenCVExecutor.gray_to_rgb(gray)

    assert rgb.shape == (2, 3, 3)
    assert np.array_equal(rgb[:, :, 0], rgb[:, :, 2])


def test_rotate_crop_returns_the_requested_crop_size() -> None:
    """旋转裁切按 (宽度, 高度) 返回指定尺寸的图片。"""
    image = _rgb(128)

    cropped = OpenCVExecutor.rotate_crop(image, (5.0, 4.0), (4, 2), 0.0)

    assert cropped.shape == (2, 4, 3)
    assert np.allclose(cropped, 128, atol=2)


def test_match_template_locates_patches_and_handles_oversize_templates() -> None:
    """模板大于搜索图时返回零分，三通道与灰度图都能定位到左上角坐标。"""
    image = _rgb()
    score, location = OpenCVExecutor.match_template(image, np.zeros((20, 20, 3), dtype=np.uint8))

    assert score == 0.0
    assert location == (0, 0)

    rng = np.random.default_rng(7)
    color_image = rng.integers(0, 255, size=(24, 24, 3), dtype=np.uint8)
    color_template = color_image[4:9, 6:11].copy()

    score, location = OpenCVExecutor.match_template(color_image, color_template)

    assert score > 0.99
    assert location == (6, 4)

    gray_image = rng.integers(0, 255, size=(20, 20), dtype=np.uint8)
    gray_template = gray_image[2:5, 3:6].copy()

    score, location = OpenCVExecutor.match_template(gray_image, gray_template)

    assert score > 0.99
    assert location == (3, 2)
