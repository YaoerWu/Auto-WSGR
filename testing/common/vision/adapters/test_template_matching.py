"""模块功能：验证模板匹配适配层的 ROI 校验、模板加载与匹配流程。

直接调用方：common.vision.service 的 expect_template / expect_template_center。
直接依赖：ROI、Template、load_template、match_template、match_templates。
边界：不读取真实模板文件，OpenCV 执行器由替身接管。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from autowsgr.common.vision.adapters import template_matching
from autowsgr.common.vision.adapters.template_matching import (
    ROI,
    Template,
    load_template,
    match_template,
    match_templates,
)


def _solid_image(height: int = 8, width: int = 10, value: int = 0) -> np.ndarray:
    """构造指定尺寸的纯色画面。"""
    return np.full((height, width, 3), value, dtype=np.uint8)


def test_roi_validates_range_and_converts_coordinates() -> None:
    """横纵坐标必须落在合法区间，换算按宽高取像素，裁切结果不共享内存。"""
    for x1, x2 in ((0.5, 0.5), (0.6, 0.4)):
        with pytest.raises(ValueError, match='ROI 横坐标必须满足'):
            ROI(x1, 0.0, x2, 1.0)
    for y1, y2 in ((0.5, 0.5), (0.6, 0.4)):
        with pytest.raises(ValueError, match='ROI 纵坐标必须满足'):
            ROI(0.0, y1, 1.0, y2)

    assert ROI(0.25, 0.5, 0.75, 1.0).to_absolute(80, 60) == (20, 30, 60, 60)

    image = np.arange(6 * 8 * 3, dtype=np.uint8).reshape(6, 8, 3)
    cropped = ROI(0.25, 0.5, 0.75, 1.0).crop(image)
    assert np.array_equal(cropped, image[3:6, 2:6])
    cropped[0, 0] = 0
    assert image[3, 2].any()


def test_load_template_resolves_root_and_limits_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """加载走执行器的相对路径，默认名称取文件名、基准分辨率为 1280x720，绝对与越界路径拒绝。"""
    image = _solid_image(2, 4)
    requested: list[Path] = []
    monkeypatch.setattr(
        template_matching._EXECUTOR,
        'load_image',
        lambda relative: requested.append(relative) or image,
    )

    template = load_template('controller/home/button.png')

    assert template.name == 'button'
    assert template.relative_path == 'controller/home/button.png'
    assert template.source_resolution == (1280, 720)
    assert np.array_equal(template.image, image)
    assert requested == [Path('controller/home/button.png')]

    overridden = load_template(
        Path('controller/home/button.png'),
        name='home_button',
        source_resolution=(1920, 1080),
    )
    assert overridden.name == 'home_button'
    assert overridden.relative_path == 'controller/home/button.png'
    assert overridden.source_resolution == (1920, 1080)

    for relative_path in ('C:/templates/button.png', '../outside/button.png'):
        with pytest.raises(ValueError, match='模板路径必须是 OPENCV_TEMPLATE_ROOT 下的相对路径'):
            load_template(relative_path)


def test_match_template_reports_hit_or_miss_after_scaling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """置信度越界报错，命中返回绝对位置与归一化中心，分辨率变化先缩放模板，分数不足不算命中。"""
    template = Template('probe', 'probe.png', _solid_image(2, 4))
    for confidence in (-0.1, 1.1):
        with pytest.raises(ValueError, match='匹配置信度必须位于'):
            match_template(_solid_image(), template, confidence=confidence)

    image = _solid_image(8, 10)
    scaled = Template('probe', 'probe.png', _solid_image(2, 4), source_resolution=(10, 8))
    monkeypatch.setattr(template_matching._EXECUTOR, 'match_template', lambda *_: (0.95, (4, 6)))

    result = match_template(image, scaled, confidence=0.9)
    assert result.matched is True
    assert result.score == 0.95
    assert result.location == (4, 6)
    assert result.center == (0.6, 0.875)
    assert result.template_path == 'probe.png'

    roi = ROI(0.5, 0.5, 1.0, 1.0)
    monkeypatch.setattr(template_matching._EXECUTOR, 'match_template', lambda *_: (1.0, (1, 1)))
    offset = match_template(image, scaled, roi=roi)
    assert offset.roi is roi
    assert offset.location == (6, 5)
    assert offset.center == (0.8, 0.75)

    resized: list[tuple[tuple[int, ...], int, int]] = []
    matched: list[tuple[int, ...]] = []

    def fake_resize(source: np.ndarray, width: int, height: int, **_: object) -> np.ndarray:
        resized.append((source.shape, width, height))
        return np.zeros((height, width, 3), dtype=np.uint8)

    def fake_match(
        _search: np.ndarray, scaled_template: np.ndarray
    ) -> tuple[float, tuple[int, int]]:
        matched.append(scaled_template.shape)
        return 1.0, (2, 2)

    monkeypatch.setattr(template_matching._EXECUTOR, 'resize', fake_resize)
    monkeypatch.setattr(template_matching._EXECUTOR, 'match_template', fake_match)

    enlarged = match_template(_solid_image(16, 20), scaled)
    assert resized == [((2, 4, 3), 8, 4)]
    assert matched == [(4, 8, 3)]
    assert enlarged.center == (0.3, 0.25)

    monkeypatch.setattr(template_matching._EXECUTOR, 'match_template', lambda *_: (0.5, (0, 0)))
    miss = match_template(_solid_image(), scaled, confidence=0.85)
    assert miss.matched is False
    assert miss.center is None


def test_match_templates_apply_shared_or_per_template_roi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """共享区域对每个模板生效，区域序列按位置一一对应，单模板可省略序列。"""
    calls: list[tuple[str, ROI | None, float]] = []

    def fake_match(
        _image: np.ndarray, template: Template, *, roi: ROI | None, confidence: float
    ) -> SimpleNamespace:
        calls.append((template.name, roi, confidence))
        return SimpleNamespace(template_path=template.relative_path)

    monkeypatch.setattr(template_matching, 'match_template', fake_match)
    roi = ROI(0.0, 0.0, 0.5, 0.5)
    first = Template('a', 'a.png', _solid_image())
    second = Template('b', 'b.png', _solid_image())

    results = match_templates(_solid_image(), (first, second), roi=roi, confidence=0.7)
    assert calls == [('a', roi, 0.7), ('b', roi, 0.7)]
    assert [result.template_path for result in results] == ['a.png', 'b.png']

    calls.clear()
    match_templates(_solid_image(), (first, second), roi=(roi, None))
    single = Template('c', 'c.png', _solid_image())
    match_templates(_solid_image(), single)
    assert calls == [('a', roi, 0.85), ('b', None, 0.85), ('c', None, 0.85)]


def test_match_templates_validate_arguments() -> None:
    """模板与区域参数按单模板/模板序列分别校验，长度不一致或类型错误都拒绝。"""
    first = Template('a', 'a.png', _solid_image())
    second = Template('b', 'b.png', _solid_image())

    with pytest.raises(ValueError, match='templates 序列不能为空'):
        match_templates(_solid_image(), [])

    with pytest.raises(TypeError, match='templates 序列中的元素必须是 Template'):
        match_templates(_solid_image(), (first, 'a.png'))

    for templates in (42, 'a.png', b'a.png'):
        with pytest.raises(TypeError, match='templates 必须是 Template 或 Template 序列'):
            match_templates(_solid_image(), templates)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match='单模板的 roi 必须是 ROI 或 None'):
        match_templates(_solid_image(), first, roi='area')  # type: ignore[arg-type]

    with pytest.raises(ValueError, match='roi 序列长度必须与 templates 序列一致'):
        match_templates(_solid_image(), (first, second), roi=(ROI(0, 0, 1, 1),))

    with pytest.raises(TypeError, match='roi 序列中的元素必须是 ROI 或 None'):
        match_templates(_solid_image(), (first, second), roi=(ROI(0, 0, 1, 1), 'area'))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match='roi 必须是 ROI、ROI 序列或 None'):
        match_templates(_solid_image(), (first, second), roi=42)  # type: ignore[arg-type]
