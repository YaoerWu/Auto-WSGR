"""模块功能：验证 YAML 与图像的允许目录校验、原子写入和读写往返。

直接调用方：项目测试运行器。

直接依赖：pytest、numpy、autowsgr.common.system.files。

边界：只在临时目录内读写文件，不触碰项目资源与真实配置。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy
import pytest

from autowsgr.common.system import files
from autowsgr.common.system.files import load_image, load_yaml, save_image, save_yaml


if TYPE_CHECKING:
    from pathlib import Path


def _temporary_files(directory: Path) -> list[Path]:
    """列出目录内由原子写入留下的临时文件。"""
    return list(directory.glob('.*.tmp'))


def test_yaml_roundtrip_creates_parent_directories_and_blank_reads_empty(tmp_path: Path) -> None:
    """YAML 写入按需建目录且不留临时文件，空文件读作空映射。"""
    target = tmp_path / 'nested' / 'task.yaml'
    mapping = {'任务': '出征', 'count': 3, 'flags': [True, False]}
    save_yaml(mapping, target, allowed_root=tmp_path)

    assert target.is_file()
    assert load_yaml(target, allowed_root=tmp_path) == mapping
    assert _temporary_files(target.parent) == []

    blank = tmp_path / 'empty.yaml'
    blank.write_text('', encoding='utf-8')
    assert load_yaml(blank, allowed_root=tmp_path) == {}


def test_missing_yaml_and_outside_root_are_rejected(tmp_path: Path) -> None:
    """读取不存在的文件报目标路径，读写越界都在落盘前拒绝。"""
    with pytest.raises(FileNotFoundError, match='YAML 文件不存在'):
        load_yaml(tmp_path / 'missing.yaml', allowed_root=tmp_path)

    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside.yaml'
    with pytest.raises(ValueError, match='路径超出允许目录'):
        load_yaml(outside, allowed_root=root)
    with pytest.raises(ValueError, match='路径超出允许目录'):
        save_yaml({'a': 1}, outside, allowed_root=root)
    assert not outside.exists()


def test_failed_replace_keeps_original_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """替换失败时不破坏原文件，也不留下临时文件。"""
    target = tmp_path / 'task.yaml'
    save_yaml({'version': 1}, target, allowed_root=tmp_path)

    monkeypatch.setattr(
        files.os, 'replace', lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('磁盘已满'))
    )
    with pytest.raises(OSError, match='磁盘已满'):
        save_yaml({'version': 2}, target, allowed_root=tmp_path)

    assert load_yaml(target, allowed_root=tmp_path) == {'version': 1}
    assert _temporary_files(tmp_path) == []


def test_image_roundtrip_preserves_rgb_and_expands_grayscale(tmp_path: Path) -> None:
    """彩色图像按 RGB 顺序往返，灰度数组读回为三通道同值。"""
    target = tmp_path / 'frame.png'
    image = numpy.zeros((3, 4, 3), dtype=numpy.uint8)
    image[0, 0] = (10, 20, 30)
    image[2, 3] = (200, 100, 50)
    save_image(image, target, allowed_root=tmp_path)

    loaded = load_image(target, allowed_root=tmp_path)
    assert loaded.shape == (3, 4, 3)
    assert tuple(loaded[0, 0]) == (10, 20, 30)
    assert tuple(loaded[2, 3]) == (200, 100, 50)

    gray_target = tmp_path / 'gray.png'
    save_image(numpy.full((2, 2), 128, dtype=numpy.uint8), gray_target, allowed_root=tmp_path)
    gray_loaded = load_image(gray_target, allowed_root=tmp_path)

    assert gray_loaded.shape == (2, 2, 3)
    assert numpy.array_equal(gray_loaded[..., 0], gray_loaded[..., 1])
    assert numpy.array_equal(gray_loaded[..., 1], gray_loaded[..., 2])


def test_corrupt_and_missing_image_are_reported(tmp_path: Path) -> None:
    """内容不是图像时给出解码失败，文件不存在时报目标路径。"""
    broken = tmp_path / 'broken.png'
    broken.write_text('not an image', encoding='utf-8')
    with pytest.raises(ValueError, match='无法解码图像文件'):
        load_image(broken, allowed_root=tmp_path)

    with pytest.raises(FileNotFoundError, match='图像文件不存在'):
        load_image(tmp_path / 'missing.png', allowed_root=tmp_path)
