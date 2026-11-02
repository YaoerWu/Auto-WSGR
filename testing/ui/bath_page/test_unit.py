"""模块功能：验证浴室页面模块边界和修理流程。

上层调用：
- pytest：执行页面入口、识别委托和修理流程回归。

下层依赖：
- bath_page.page、operations、recognition：提供被测页面能力。
- common.types、common.vision：提供测试结果类型和截图事实类型。

边界：
本模块只使用 mock 控制器和内存截图，不连接真实设备，不验证实机页面契约。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from autowsgr.application.controller.backyard.bath import BathPage
from autowsgr.application.ui.controller.backyard.bath_page import page as page_module
from autowsgr.application.ui.controller.backyard.bath_page import recognition
from autowsgr.application.ui.controller.backyard.bath_page.recognition import RepairShipInfo
from autowsgr.common.types import PageName
from autowsgr.common.vision import PageMatch


def _screen() -> np.ndarray:
    """返回最小的 RGB 测试截图。"""
    return np.zeros((540, 960, 3), dtype=np.uint8)


def test_page_recognition_entry_delegates_to_lower_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面检查入口只委托给 recognition，不复制视觉实现。"""
    screen = _screen()
    expected = PageMatch(name=PageName.BATH.value, matched=True, score=0.9)
    checker = MagicMock(return_value=expected)
    monkeypatch.setattr(recognition, 'check_current_page', checker)

    assert BathPage.check_current_page(screen) is expected
    checker.assert_called_once_with(screen)


def test_recognition_page_check_prefers_bath_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """浴室基础模板命中时返回对应页面事实。"""
    detail = SimpleNamespace(confidence=0.91)
    finder = MagicMock(return_value=detail)
    monkeypatch.setattr(recognition.ImageChecker, 'find_template', finder)

    result = recognition.check_current_page(_screen())

    assert result == PageMatch(name=PageName.BATH.value, matched=True, score=0.91)
    finder.assert_called_once()


def test_recognize_repair_card_uses_public_ocr_name_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """卡片识别通过 OCR 公开舰名接口读取名称。"""
    screen = np.zeros((400, 960, 3), dtype=np.uint8)
    monkeypatch.setattr(recognition, '_detect_card_rects', lambda _image: [(10, 0, 174, 400)])
    ocr = MagicMock()
    ocr.recognize_ship_name.return_value = '测试舰'
    ocr.recognize.return_value = []

    cards = recognition.recognize_repair_cards(screen, ocr)

    assert len(cards) == 1
    assert cards[0].name == '测试舰'
    assert cards[0].repair_time == ''
    ocr.recognize_ship_name.assert_called_once()


def test_repair_all_clicks_top_right_entry_and_all_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=MagicMock())
    ctx.ctrl.screenshot.return_value = _screen()
    overlay_check = MagicMock(side_effect=[False, False])
    click_choose = MagicMock()
    click_all = MagicMock()
    monkeypatch.setattr(page_module.recognition, 'check_choose_repair_overlay', overlay_check)
    monkeypatch.setattr(
        page_module.recognition, 'check_repair_all_available', MagicMock(return_value=True)
    )
    monkeypatch.setattr(
        page_module.recognition,
        'check_current_page',
        MagicMock(return_value=PageMatch(PageName.BATH.value, True, 0.9)),
    )
    monkeypatch.setattr(page_module.operations, 'click_choose_repair', click_choose)
    monkeypatch.setattr(page_module.operations, 'click_repair_all', click_all)
    monkeypatch.setattr(page_module, 'wait_for_page', MagicMock())
    monkeypatch.setattr(page_module.time, 'sleep', MagicMock())

    result = BathPage(ctx).repair(repair_all=True)

    assert result is None
    click_choose.assert_called_once_with(ctx.ctrl)
    click_all.assert_called_once_with(ctx.ctrl)


def test_repair_ship_pages_until_named_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """指定舰船未在首屏时翻页，并在选中后返回修理秒数。"""
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
    ctx.ctrl.screenshot.return_value = _screen()
    recognizer = MagicMock(
        side_effect=[
            [RepairShipInfo(f'其他舰{i}', (0.1, 0.5), '00:00:10') for i in range(5)],
            [RepairShipInfo('目标舰', (0.2, 0.5), '01:02:03')],
        ]
    )
    monkeypatch.setattr(
        page_module.recognition, 'check_choose_repair_overlay', MagicMock(return_value=True)
    )
    monkeypatch.setattr(page_module, 'wait_for_page', MagicMock())
    monkeypatch.setattr(page_module.recognition, 'recognize_repair_cards', recognizer)
    swipe = MagicMock()
    click = MagicMock()
    monkeypatch.setattr(page_module.operations, 'swipe_repair_list', swipe)
    monkeypatch.setattr(page_module.operations, 'click_repair_card', click)
    monkeypatch.setattr(page_module.operations, 'wait_overlay_closed', MagicMock(return_value=True))

    result = BathPage(ctx).repair(repair_all=False, ship_name='目标舰')

    assert result == 3723
    swipe.assert_called_once_with(ctx.ctrl)
    click.assert_called_once_with(ctx.ctrl, (0.2, 0.5))
    assert recognizer.call_count == 2
    recognizer.assert_any_call(ctx.ctrl.screenshot.return_value, ctx.ocr)


def test_repair_ship_reports_missing_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """目标舰船不存在时返回可供业务层区分的失败类型。"""
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
    ctx.ctrl.screenshot.return_value = _screen()
    monkeypatch.setattr(
        page_module.recognition, 'check_choose_repair_overlay', MagicMock(return_value=True)
    )
    monkeypatch.setattr(page_module, 'wait_for_page', MagicMock())
    monkeypatch.setattr(
        page_module.recognition, 'recognize_repair_cards', MagicMock(return_value=[])
    )

    with pytest.raises(LookupError):
        BathPage(ctx).repair(repair_all=False, ship_name='目标舰')


def test_repair_longest_reports_full_bath(monkeypatch: pytest.MonkeyPatch) -> None:
    """目标点击后浮层未关闭时返回浴场已满标记。"""
    ctx = SimpleNamespace(ctrl=MagicMock(), ocr=object())
    ctx.ctrl.screenshot.return_value = _screen()
    monkeypatch.setattr(
        page_module.recognition, 'check_choose_repair_overlay', MagicMock(return_value=True)
    )
    monkeypatch.setattr(page_module, 'wait_for_page', MagicMock())
    monkeypatch.setattr(
        page_module.recognition,
        'recognize_repair_cards',
        MagicMock(
            return_value=[
                RepairShipInfo('目标舰', (0.2, 0.5), '00:10:00'),
            ]
        ),
    )
    click = MagicMock()
    monkeypatch.setattr(page_module.operations, 'click_repair_card', click)
    monkeypatch.setattr(
        page_module.operations, 'wait_overlay_closed', MagicMock(return_value=False)
    )

    result = BathPage(ctx).repair(repair_all=False)

    assert result == ('', -2)
    click.assert_called_once_with(ctx.ctrl, (0.2, 0.5))


def test_go_back_keeps_navigation_in_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """页面级返回保留在 BathPage，并只调用基础返回操作。"""
    from autowsgr.application.ui.controller.backyard.bath_page import page as page_module

    ctrl = MagicMock()
    ctrl.screenshot.return_value = _screen()
    bath_page = BathPage(SimpleNamespace(ctrl=ctrl, ocr=MagicMock()))
    page_check = MagicMock(return_value=PageMatch(PageName.BATH.value, True, 0.9))
    overlay_check = MagicMock(return_value=False)
    click_back = MagicMock()
    wait_leave = MagicMock()
    monkeypatch.setattr(page_module.BathPage, 'check_current_page', staticmethod(page_check))
    monkeypatch.setattr(page_module.recognition, 'check_choose_repair_overlay', overlay_check)
    monkeypatch.setattr(page_module.operations, 'click_back', click_back)
    monkeypatch.setattr(page_module, 'wait_leave_page', wait_leave)

    bath_page.go_back()

    click_back.assert_called_once_with(ctrl)
    wait_leave.assert_called_once()
    assert wait_leave.call_args.args[0] is ctrl
    assert wait_leave.call_args.kwargs['source'] == '浴室'
