"""验证 common.vision 包只导出稳定识别入口与数据模型。

直接调用方：application、business、dispatch 和 server 按包级入口使用视觉能力。
直接依赖：autowsgr.common.vision.__init__ 的导出声明。
边界：只校验导出面，不初始化 OCR 模型或设备。
"""

from __future__ import annotations

from autowsgr.common import vision
from autowsgr.common.vision.adapters import pixel_matching, template_matching
from autowsgr.common.vision.ocr import TextDetection


def test_package_exports_every_public_entry() -> None:
    """包级导出覆盖识别入口、识别结果模型和识别配置。"""
    assert set(vision.__all__) == {
        'ROI',
        'Color',
        'CompositePixelSignature',
        'MatchStrategy',
        'PixelDetail',
        'PixelMatchResult',
        'PixelRule',
        'PixelSignature',
        'RecognitionProfile',
        'RecognitionResult',
        'Template',
        'TemplateMatchResult',
        'TextDetection',
        'expect_ocr',
        'expect_ocr_center',
        'expect_pixel_center',
        'expect_pixels',
        'expect_template',
        'expect_template_center',
        'screenshot',
    }


def test_package_reexports_the_owning_data_models() -> None:
    """包级模型对象与所属子模块中的定义是同一对象。"""
    assert vision.ROI is template_matching.ROI
    assert vision.Template is template_matching.Template
    assert vision.PixelSignature is pixel_matching.PixelSignature
    assert vision.TextDetection is TextDetection


def test_recognition_entries_are_callable() -> None:
    """所有识别入口都是可调用对象。"""
    for name in (
        'screenshot',
        'expect_template',
        'expect_template_center',
        'expect_ocr',
        'expect_ocr_center',
        'expect_pixels',
        'expect_pixel_center',
    ):
        assert callable(getattr(vision, name))
