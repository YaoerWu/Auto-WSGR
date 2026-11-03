"""验证 FastOCR 执行器的初始化与结果标准化流程。

直接调用方：adapters.text_recognition 通过 recognize / recognize_line 取文字。

直接依赖：MaaFramework 运行时、OpenCV 通道转换与 common.vision.config。

边界：用假 MaaFramework 模块替身，绝不加载真实模型或初始化 OCR 运行时。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from autowsgr.common.vision import config
from autowsgr.common.vision.ocr.executor import OCRExecutor, TextDetection


class _Options:
    """记录识别选项的假 JOCR。"""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _Job:
    """假识别任务，可控制成功状态与详情。"""

    def __init__(self, *, succeeded: bool = True, detail: object = None) -> None:
        self.succeeded = succeeded
        self._detail = detail

    def wait(self) -> _Job:
        return self

    def get(self) -> object:
        return self._detail


class _Tasker:
    """记录识别请求的假任务执行器。"""

    def __init__(self, job: _Job) -> None:
        self.job = job
        self.posts: list[tuple[object, object, np.ndarray]] = []

    def post_recognition(
        self, recognition_type: object, options: object, image: np.ndarray
    ) -> _Job:
        self.posts.append((recognition_type, options, image))
        return self.job


def _executor(tasker: _Tasker, *, threshold: float = 0.5) -> OCRExecutor:
    """绕过 __init__ 构造只带识别所需字段的执行器。"""
    executor = object.__new__(OCRExecutor)
    executor._tasker = tasker
    executor._threshold = threshold
    executor._recognition_type = 'ocr'
    executor._ocr_options_type = _Options
    return executor


def _detection(text: str, score: float, box: tuple[float, float, float, float]) -> SimpleNamespace:
    """构造假 detection 对象。"""
    return SimpleNamespace(text=text, score=score, box=box)


def _detail(*nodes: object) -> SimpleNamespace:
    """构造假识别详情。"""
    return SimpleNamespace(nodes=list(nodes))


def _node(*detections: SimpleNamespace, recognition: object = ...) -> SimpleNamespace:
    """构造假识别节点，默认带 filtered_results。"""
    resolved = (
        SimpleNamespace(filtered_results=list(detections)) if recognition is ... else recognition
    )
    return SimpleNamespace(recognition=resolved)


def test_recognize_converts_bgr_and_standardizes_results() -> None:
    """完整识别提交 BGR 图与阈值选项，结果按先纵后横排序并四舍五入区域。"""
    detail = _detail(
        _node(
            _detection('right', 0.9, (50.0, 10.0, 1.0, 1.0)),
            _detection('second-row', 0.9, (2.0, 30.0, 1.0, 1.0)),
            _detection('left', 0.9, (5.0, 10.0, 1.0, 1.0)),
            _detection('go', 0.9, (1.6, 2.4, 3.2, 4.4)),
        )
    )
    tasker = _Tasker(_Job(detail=detail))
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[:, :] = (10, 20, 30)

    result = _executor(tasker, threshold=0.7).recognize(image)

    recognition_type, options, submitted = tasker.posts[0]
    assert recognition_type == 'ocr'
    assert options.kwargs == {'only_rec': False, 'threshold': 0.7}
    assert submitted.tolist() == [[[30, 20, 10], [30, 20, 10]], [[30, 20, 10], [30, 20, 10]]]
    assert [detection.recognized_text for detection in result] == [
        'go',
        'left',
        'right',
        'second-row',
    ]
    assert TextDetection('go', 0.9).text_region is None
    assert result[0].text_region == (2, 2, 5, 7)


def test_recognize_line_and_allowlist_filtering() -> None:
    """单行识别跳过检测阶段，allowlist 逐字符过滤并丢弃空文本与无识别节点。"""
    tasker = _Tasker(_Job(detail=_detail()))
    _executor(tasker).recognize_line(np.zeros((1, 1, 3), dtype=np.uint8))

    assert tasker.posts[0][1].kwargs == {'only_rec': True, 'threshold': 0.5}

    filtering_tasker = _Tasker(
        _Job(
            detail=_detail(
                _node(
                    _detection('a1b2', 0.9, (0.0, 0.0, 1.0, 1.0)),
                    _detection('123', 0.8, (0.0, 2.0, 1.0, 1.0)),
                    _detection('', 0.7, (0.0, 4.0, 1.0, 1.0)),
                )
            )
        )
    )
    filtered = _executor(filtering_tasker).recognize(
        np.zeros((1, 1, 3), dtype=np.uint8), allowlist='ab'
    )

    assert [detection.recognized_text for detection in filtered] == ['ab']

    empty_tasker = _Tasker(_Job(detail=_detail(_node(recognition=None))))
    assert _executor(empty_tasker).recognize(np.zeros((1, 1, 3), dtype=np.uint8)) == []


def test_recognize_reports_task_failures() -> None:
    """任务失败或缺少详情时直接报错，不返回空结果掩盖失败。"""
    with pytest.raises(RuntimeError, match='FastOCR 识别任务失败'):
        _executor(_Tasker(_Job(succeeded=False))).recognize(np.zeros((1, 1, 3), dtype=np.uint8))

    with pytest.raises(RuntimeError, match='FastOCR 未返回识别详情'):
        _executor(_Tasker(_Job(detail=None))).recognize(np.zeros((1, 1, 3), dtype=np.uint8))


def _install_maa(
    monkeypatch: pytest.MonkeyPatch,
    *,
    toolkit_ok: bool = True,
    binding_ok: bool = True,
) -> SimpleNamespace:
    """注入假 MaaFramework 模块并返回可断言的记录。"""
    records = SimpleNamespace(toolkit_calls=[], bind_calls=[], model_dir=None)

    class _ModelJob:
        succeeded = True

    class _Submitted:
        def wait(self) -> _ModelJob:
            return _ModelJob()

    class _Resource:
        def __init__(self) -> None:
            self._handle = 'resource-handle'

        def use_cpu(self) -> bool:
            return True

        def post_ocr_model(self, model_dir: Path) -> _Submitted:
            records.model_dir = Path(model_dir)
            return _Submitted()

    class _TaskerImpl:
        def __init__(self) -> None:
            self._handle = 'tasker-handle'
            self.inited = True
            self._resource_holder = None

    class _Framework:
        @staticmethod
        def MaaTaskerBindResource(tasker_handle: object, resource_handle: object) -> bool:
            records.bind_calls.append((tasker_handle, resource_handle))
            return binding_ok

    class _Library:
        @staticmethod
        def framework() -> _Framework:
            return _Framework()

    class _Toolkit:
        @staticmethod
        def init_option(user_dir: Path, options: dict[str, object]) -> bool:
            records.toolkit_calls.append((Path(user_dir), options))
            return toolkit_ok

    class _JOCR(_Options):
        pass

    class _JRecognitionType:
        OCR = 'ocr-recognition'

    modules = {
        'maa': types.ModuleType('maa'),
        'maa.library': types.ModuleType('maa.library'),
        'maa.pipeline': types.ModuleType('maa.pipeline'),
        'maa.resource': types.ModuleType('maa.resource'),
        'maa.tasker': types.ModuleType('maa.tasker'),
        'maa.toolkit': types.ModuleType('maa.toolkit'),
    }
    package = modules['maa']
    package.__path__ = []  # type: ignore[attr-defined]
    modules['maa.library'].Library = _Library  # type: ignore[attr-defined]
    modules['maa.library'].framework = _Library.framework  # type: ignore[attr-defined]
    modules['maa.pipeline'].JOCR = _JOCR  # type: ignore[attr-defined]
    modules['maa.pipeline'].JRecognitionType = _JRecognitionType  # type: ignore[attr-defined]
    modules['maa.resource'].Resource = _Resource  # type: ignore[attr-defined]
    modules['maa.tasker'].Tasker = _TaskerImpl  # type: ignore[attr-defined]
    modules['maa.toolkit'].Toolkit = _Toolkit  # type: ignore[attr-defined]
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        if name != 'maa':
            setattr(package, name.split('.', 1)[1], module)
    return records


def _prepare_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把模型目录与用户目录都指向临时目录。"""
    model_dir = tmp_path / 'models'
    model_dir.mkdir()
    user_dir = tmp_path / 'user'
    monkeypatch.setenv(config.OCR_MODEL_DIR_ENV, str(model_dir))
    monkeypatch.setenv(config.OCR_USER_DIR_ENV, str(user_dir))
    return model_dir


def test_init_requires_model_files_and_valid_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """初始化检查模型文件、创建用户目录并解析阈值环境变量。"""
    _install_maa(monkeypatch)
    model_dir = _prepare_environment(monkeypatch, tmp_path)

    with pytest.raises(
        RuntimeError, match=r'FastOCR 模型目录缺少文件: det\.onnx, rec\.onnx, keys\.txt'
    ):
        OCRExecutor()

    assert not model_dir.joinpath('det.onnx').exists()

    for name in config.OCR_MODEL_FILES:
        (model_dir / name).write_text('stub', encoding='utf-8')
    monkeypatch.setenv(config.OCR_THRESHOLD_ENV, 'high')
    with pytest.raises(RuntimeError, match=f'{config.OCR_THRESHOLD_ENV} 必须是数字'):
        OCRExecutor()

    monkeypatch.setenv(config.OCR_THRESHOLD_ENV, '0.75')
    records = _install_maa(monkeypatch)
    executor = OCRExecutor()

    assert executor._threshold == 0.75
    assert executor._recognition_type == 'ocr-recognition'
    assert executor._ocr_options_type is not None
    assert records.model_dir == model_dir
    assert records.bind_calls == [('tasker-handle', 'resource-handle')]
    assert records.toolkit_calls[0][1] == {'logging': False}
    assert (tmp_path / 'user').is_dir()


def test_init_reports_framework_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Toolkit 初始化与 Resource 绑定失败都给出明确原因。"""
    model_dir = _prepare_environment(monkeypatch, tmp_path)
    for name in config.OCR_MODEL_FILES:
        (model_dir / name).write_text('stub', encoding='utf-8')

    _install_maa(monkeypatch, toolkit_ok=False)
    with pytest.raises(RuntimeError, match='FastOCR 初始化 MaaFramework Toolkit 失败'):
        OCRExecutor()

    _install_maa(monkeypatch, binding_ok=False)
    with pytest.raises(RuntimeError, match='FastOCR 无法绑定 OCR Resource'):
        OCRExecutor()
