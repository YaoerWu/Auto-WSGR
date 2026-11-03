"""验证 common.vision 的静态识别配置。

直接调用方：common.vision 的 service、adapters、opencv、numpy 和 ocr 子模块。
直接依赖：autowsgr.common.vision.config 的模块级常量。
边界：只校验配置值与导出面，不加载图片、不执行识别。
"""

from __future__ import annotations

from pathlib import Path

from autowsgr.common.vision import config


def test_recognition_retry_defaults_are_stable() -> None:
    """识别重试默认次数与间隔保持约定值。"""
    assert config.DEFAULT_RECOGNITION_ATTEMPTS == 3
    assert config.DEFAULT_RECOGNITION_INTERVAL_SECONDS == 0.5


def test_template_configuration_points_at_packaged_resources() -> None:
    """模板根目录指向仓库 resources/image，并保持 1280x720 基准。"""
    assert (
        Path(config.__file__).resolve().parents[3] / 'resources' / 'image'
        == config.OPENCV_TEMPLATE_ROOT
    )
    assert config.OPENCV_TEMPLATE_SOURCE_RESOLUTION == (1280, 720)
    assert config.OPENCV_TEMPLATE_CONFIDENCE == 0.85


def test_pixel_and_text_defaults_are_stable() -> None:
    """像素容差、坐标边界和文本预处理参数保持约定值。"""
    assert config.NUMPY_DEFAULT_PIXEL_TOLERANCE == 30.0
    assert (config.NUMPY_COORDINATE_MIN, config.NUMPY_COORDINATE_MAX) == (0.0, 1.0)
    assert config.OPENCV_TEXT_SCALE == 4
    assert config.OPENCV_TEXT_BLUR_KERNEL == 3


def test_ocr_model_configuration_is_complete() -> None:
    """OCR 模型文件清单、环境变量名和默认阈值保持约定值。"""
    assert config.OCR_MODEL_FILES == ('det.onnx', 'rec.onnx', 'keys.txt')
    assert config.OCR_MODEL_DIR_ENV == 'AUTOWSGR_FASTOCR_MODEL_DIR'
    assert config.OCR_USER_DIR_ENV == 'AUTOWSGR_FASTOCR_USER_DIR'
    assert config.OCR_THRESHOLD_ENV == 'AUTOWSGR_FASTOCR_THRESHOLD'
    assert config.OCR_DEFAULT_THRESHOLD == 0.3


def test_config_exports_every_public_constant() -> None:
    """模块声明的 __all__ 覆盖全部公开常量。"""
    assert set(config.__all__) == {
        'DEFAULT_RECOGNITION_ATTEMPTS',
        'DEFAULT_RECOGNITION_INTERVAL_SECONDS',
        'NUMPY_COORDINATE_MAX',
        'NUMPY_COORDINATE_MIN',
        'NUMPY_DEFAULT_PIXEL_TOLERANCE',
        'OCR_DEFAULT_THRESHOLD',
        'OCR_MODEL_DIR_ENV',
        'OCR_MODEL_FILES',
        'OCR_THRESHOLD_ENV',
        'OCR_USER_DIR_ENV',
        'OPENCV_TEMPLATE_CONFIDENCE',
        'OPENCV_TEMPLATE_ROOT',
        'OPENCV_TEMPLATE_SOURCE_RESOLUTION',
        'OPENCV_TEXT_BLUR_KERNEL',
        'OPENCV_TEXT_SCALE',
    }
    for name in config.__all__:
        assert hasattr(config, name)
