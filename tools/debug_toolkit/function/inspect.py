"""通用游戏截图 + OCR 调试工具。

连接模拟器，截图并对指定区域执行 OCR，保存所有中间图像。
适用于排查任何页面的 OCR / 像素识别问题。

使用方式::

    # 截图并交互式检查像素 / OCR
    python tools/debug_toolkit/main.py inspect

    # 指定配置文件
    python tools/debug_toolkit/main.py inspect -c usersettings.yaml

    # 从已有图片分析
    python tools/debug_toolkit/main.py inspect -i screenshot.png

    # 对指定区域做 OCR (相对坐标: x1,y1,x2,y2)
    python tools/debug_toolkit/main.py inspect --roi 0.818,0.81,0.875,0.867

    # 指定 OCR 白名单
    python tools/debug_toolkit/main.py inspect --roi 0.818,0.81,0.875,0.867 --allowlist "0123456789Ex-"

    # 检查像素签名
    python tools/debug_toolkit/main.py inspect --check-page decisive_battle

    # 保存到自定义目录
    python tools/debug_toolkit/main.py inspect -o logs/my_debug
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

import cv2

from tools.debug_toolkit.function.collect import _write_png
from tools.debug_toolkit.function.roi import _parse_roi


if TYPE_CHECKING:
    import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PACKAGE_ROOT / 'result' / 'inspect'


def _save(img: np.ndarray, name: str, out_dir: Path) -> Path:
    path = out_dir / name
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    _write_png(path, bgr)
    print(f'  保存: {path}')
    return path


def _crop(screen: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = screen.shape[:2]
    return screen[int(y1 * h) : int(y2 * h), int(x1 * w) : int(x2 * w)].copy()


def _draw_roi(
    screen: np.ndarray,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: tuple[int, int, int] = (255, 0, 0),
    label: str = '',
) -> np.ndarray:
    vis = screen.copy()
    h, w = vis.shape[:2]
    cv2.rectangle(vis, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), color, 2)
    if label:
        cv2.putText(
            vis, label, (int(x1 * w), int(y1 * h) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
        )
    return vis


def _print_pixel_info(screen: np.ndarray, rx: float, ry: float) -> None:
    h, w = screen.shape[:2]
    px, py = int(rx * w), int(ry * h)
    if 0 <= px < w and 0 <= py < h:
        r, g, b = screen[py, px]
        print(f'  像素 ({rx:.4f}, {ry:.4f}) → ({px}, {py}) → RGB({r}, {g}, {b})')


def capture_screenshot(config_path: str = 'usersettings.yaml') -> np.ndarray:
    """连接模拟器并截图。"""
    from autowsgr.application.runtime.launcher import Launcher

    print('连接模拟器...')
    launcher = Launcher(config_path=config_path)
    try:
        launcher.load_config()
        launcher.connect()
        ctx = launcher.build_context()
        print('截图...')
        return ctx.ctrl.screenshot()
    finally:
        launcher.disconnect()


def check_page_signatures(screen: np.ndarray, page_name: str | None = None) -> None:
    """检查当前截图匹配哪些页面签名。"""
    from autowsgr.common.vision import PixelChecker

    # 收集所有已知的页面签名
    known_pages = {}
    try:
        from autowsgr.application.ui.controller.operations.sortie_page.decisive_page.constants import (
            SIG_MAP_PAGE as DECISIVE_SIG,
        )

        known_pages['decisive_battle'] = DECISIVE_SIG
    except ImportError:
        pass
    try:
        from autowsgr.application.ui.controller.home.main_page.constants import (
            PAGE_SIGNATURE as MAIN_SIG,
        )

        known_pages['main'] = MAIN_SIG
    except ImportError:
        pass

    print('\n=== 页面签名检测 ===')
    for name, sig in known_pages.items():
        if page_name and name != page_name:
            continue
        result = PixelChecker.check_signature(screen, sig)
        status = '✓ 匹配' if result.matched else '✗ 不匹配'
        print(f'  {name}: {status}')
        if hasattr(result, 'details') and result.details:
            for d in result.details:
                print(
                    f'    ({d.rx:.4f}, {d.ry:.4f}): '
                    f'期望 {d.expected} 实际 {d.actual} '
                    f'距离={d.distance:.1f} {"✓" if d.passed else "✗"}'
                )


def run_ocr_on_roi(
    screen: np.ndarray,
    roi: tuple[float, float, float, float],
    allowlist: str = '',
    out_dir: Path = DEFAULT_OUTPUT_DIR,
) -> None:
    """对指定 ROI 区域执行 OCR 测试。"""
    from autowsgr.common.vision import RecognitionProfile
    from autowsgr.common.vision import ocr as run_ocr

    x1, y1, x2, y2 = roi
    cropped = _crop(screen, x1, y1, x2, y2)
    print(f'\nROI: ({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f})')
    print(f'裁切尺寸: {cropped.shape[1]}x{cropped.shape[0]}')

    _save(cropped, 'roi_crop.png', out_dir)
    enlarged = cv2.resize(cropped, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    _save(enlarged, 'roi_crop_4x.png', out_dir)
    vis = _draw_roi(screen, x1, y1, x2, y2, label='ROI')
    _save(vis, 'annotated.png', out_dir)

    print('\n初始化 OCR...')
    print('\n=== OCR: 无白名单 ===')
    results = run_ocr(cropped, recognition_profile=RecognitionProfile.FULL)
    for r in results:
        print(f"  '{r.recognized_text}' (conf={r.confidence_score:.3f})")
    if not results:
        print('  [无结果]')

    if allowlist:
        print(f'\n=== OCR: allowlist={allowlist!r} ===')
        results = run_ocr(
            cropped,
            allowlist=allowlist,
            recognition_profile=RecognitionProfile.FULL,
        )
        for r in results:
            print(f"  '{r.recognized_text}' (conf={r.confidence_score:.3f})")
        if not results:
            print('  [无结果]')

    print('\n=== OCR: 放大 4x 无白名单 ===')
    results = run_ocr(enlarged, recognition_profile=RecognitionProfile.FULL)
    for r in results:
        print(f"  '{r.recognized_text}' (conf={r.confidence_score:.3f})")
    if not results:
        print('  [无结果]')


def _parse_pixel(value: str) -> tuple[float, float]:
    try:
        values = tuple(float(item) for item in value.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('像素坐标必须是 rx,ry') from exc
    if len(values) != 2 or not all(0.0 <= item <= 1.0 for item in values):
        raise argparse.ArgumentTypeError('像素坐标必须在 [0, 1]')
    return values


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """注册截图、OCR、像素和页面签名诊断参数。"""
    parser.add_argument('-c', '--config', type=Path, default=Path('usersettings.yaml'))
    parser.add_argument('-i', '--image', type=Path, help='从本地图片加载（跳过连接）')
    parser.add_argument('-o', '--output', type=Path, default=DEFAULT_OUTPUT_DIR, help='输出目录')
    parser.add_argument('--roi', type=_parse_roi, help='OCR 区域（x1,y1,x2,y2 相对坐标）')
    parser.add_argument('--allowlist', default='', help='OCR 字符白名单')
    parser.add_argument('--check-page', default=None, help='检查页面签名（如 decisive_battle）')
    parser.add_argument('--pixel', action='append', type=_parse_pixel, help='查询像素点（rx,ry）')


def run(args: argparse.Namespace) -> int:
    """执行统一工具入口传入的截图诊断命令。"""
    out_dir = args.output

    if args.image:
        bgr = cv2.imread(str(args.image))
        if bgr is None:
            raise FileNotFoundError(f'无法加载图片: {args.image}')
        screen = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        print(f'从图片加载: {args.image}')
    else:
        screen = capture_screenshot(str(args.config))

    print(f'截图尺寸: {screen.shape[1]}x{screen.shape[0]}')
    _save(screen, 'screenshot.png', out_dir)

    if args.pixel:
        print('\n=== 像素查询 ===')
        for rx, ry in args.pixel:
            _print_pixel_info(screen, rx, ry)

    if args.check_page is not None:
        check_page_signatures(screen, args.check_page)

    if args.roi:
        run_ocr_on_roi(screen, args.roi, allowlist=args.allowlist, out_dir=out_dir)

    if not args.roi and args.check_page is None and not args.pixel:
        print('\n提示: 使用 --roi / --check-page / --pixel 执行进一步分析')
        print(f'截图已保存到: {out_dir.resolve()}')
        check_page_signatures(screen)
    return 0


def main(argv: list[str] | None = None) -> int:
    """独立执行截图诊断命令。"""
    parser = argparse.ArgumentParser(
        description='通用游戏截图 + OCR 调试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
