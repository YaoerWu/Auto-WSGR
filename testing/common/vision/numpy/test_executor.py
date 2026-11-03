"""验证 NumPy 执行器的图片校验、坐标换算、采样与裁切流程。

直接调用方：adapters.pixel_matching 通过它读取相对坐标上的像素。

直接依赖：NumPy 与 common.vision.config 的坐标边界。

边界：只验证数组级行为，不涉及像素匹配策略。
"""

from __future__ import annotations

import numpy as np
import pytest

from autowsgr.common.vision.numpy.executor import NumpyExecutor


def _image() -> np.ndarray:
    """构造 10 行 20 列的图片，像素值等于其坐标组合便于断言。"""
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    for row in range(10):
        for column in range(20):
            image[row, column] = (row, column, 7)
    return image


def test_validate_image_reports_dimensions_and_rejects_bad_shapes() -> None:
    """合法图片返回 (高度, 宽度)，形状与空尺寸非法时拒绝。"""
    assert NumpyExecutor.validate_image(_image()) == (10, 20)

    cases = [
        (np.zeros((10, 20), dtype=np.uint8), '视觉图片必须是 HxWx3 的 RGB 数组'),
        (np.zeros((10, 20, 2), dtype=np.uint8), '视觉图片必须是 HxWx3 的 RGB 数组'),
        (np.zeros((0, 20, 3), dtype=np.uint8), '视觉图片不能为空'),
        (np.zeros((10, 0, 3), dtype=np.uint8), '视觉图片不能为空'),
    ]
    for image, message in cases:
        with pytest.raises(ValueError, match=message):
            NumpyExecutor.validate_image(image)


def test_coordinate_index_maps_and_clamps_coordinates() -> None:
    """相对坐标换成整数索引，右上角钳制到最后一格，越界直接拒绝。"""
    assert NumpyExecutor.coordinate_index(_image(), 0.5, 0.5) == (10, 5)
    assert NumpyExecutor.coordinate_index(_image(), 1.0, 1.0) == (19, 9)

    for x, y in ((-0.1, 0.5), (0.5, 1.1)):
        with pytest.raises(ValueError, match=r'像素坐标必须位于 \[0, 1\]'):
            NumpyExecutor.coordinate_index(_image(), x, y)


def test_sample_pixels_returns_rows_in_request_order() -> None:
    """单点与批量采样都按请求顺序返回 RGB，空请求返回空数组。"""
    assert NumpyExecutor.sample_pixel(_image(), 0.5, 0.5) == (5, 10, 7)

    pixels = NumpyExecutor.sample_pixels(_image(), [(0.0, 0.0), (0.5, 0.5)])

    assert pixels.shape == (2, 3)
    assert pixels[0].tolist() == [0, 0, 7]
    assert pixels[1].tolist() == [5, 10, 7]

    empty = NumpyExecutor.sample_pixels(_image(), [])

    assert empty.shape == (0, 3)
    assert empty.dtype == np.uint8


def test_sample_pixels_rejects_malformed_or_out_of_range_positions() -> None:
    """坐标项必须是二元组，任一分量越界都拒绝整批采样。"""
    with pytest.raises(ValueError, match=r'像素坐标必须是 \(x, y\) 序列'):
        NumpyExecutor.sample_pixels(_image(), [(0.5,)])

    with pytest.raises(ValueError, match=r'像素坐标必须位于 \[0, 1\]'):
        NumpyExecutor.sample_pixels(_image(), [(0.5, 0.5), (1.5, 0.5)])


def test_crop_returns_an_independent_copy() -> None:
    """裁切按相对坐标取子图，且不与原图共享内存。"""
    image = _image()

    cropped = NumpyExecutor.crop(image, 0.5, 0.5, 1.0, 1.0)
    cropped[0, 0] = 255

    assert cropped.shape == (5, 10, 3)
    assert image[5, 10].tolist() == [5, 10, 7]


def test_crop_rejects_invalid_ranges() -> None:
    """裁切坐标必须满足 0 <= 起点 <= 终点 <= 1。"""
    for x1, y1, x2, y2 in (
        (-0.1, 0.0, 1.0, 1.0),
        (0.5, 0.0, 1.5, 1.0),
        (0.8, 0.0, 0.2, 1.0),
    ):
        with pytest.raises(ValueError, match='裁切坐标必须满足 0 <= 起点 <= 终点 <= 1'):
            NumpyExecutor.crop(_image(), x1, y1, x2, y2)
