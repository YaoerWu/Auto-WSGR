"""模块功能：验证活动地图页的难度判定、页面确认与章节校验流程。

直接调用方：项目测试运行器。

直接依赖：pytest、controller.event.stage_push.checker 与 vision 三路识别入口。

边界：用替身接管模板加载与识别入口，不读盘、不访问设备。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autowsgr.application.controller.event.stage_push import checker as event_checker
from autowsgr.application.controller.event.stage_push import constants as event_constants
from autowsgr.application.controller.event.stage_push.checker import (
    EventMapState,
    EventMode,
    EventStage,
    calculate_current_mode,
    check_event_entry,
    check_event_map_page,
    check_event_sortie_prepare,
    is_stage_title_matched,
    parse_stage,
    read_event_map_state,
    read_event_stage,
    read_event_type,
    read_map_title,
    read_mode_button,
    read_mode_button_center,
    read_sortie_overlay,
    read_sortie_prepare_center,
    read_stage_title_texts,
    wait_event_mode,
)
from autowsgr.application.navigation.types import NavigationError


def _match(matched: bool) -> SimpleNamespace:
    """构造一条模板命中事实。"""
    return SimpleNamespace(matched=matched, score=0.9)


def _detection(text: str) -> SimpleNamespace:
    """构造一条 OCR 识别事实。"""
    return SimpleNamespace(recognized_text=text, confidence_score=0.9)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    button: EventMode | None = None,
    title: EventMode | None = None,
    overlay: bool = False,
    titles: tuple[str, ...] = (),
    entry: bool = False,
    center: tuple[float, float] | None = (0.5, 0.5),
) -> None:
    """按测试设定接管三路识别：模式按钮、地图标题、节点浮窗。"""

    def load_template(namespace: str, filename: str) -> tuple[str, str]:
        return (namespace, filename)

    def expect_template(_ctx: object, **options: object) -> SimpleNamespace:
        template = options['template']
        # 模式按钮一次传两张模板，元素本身是 (命名空间, 文件名) 二元组。
        if isinstance(template, tuple) and isinstance(template[0], tuple):
            return SimpleNamespace(
                satisfied=button is not None,
                observation=[_match(button is EventMode.NORMAL), _match(button is EventMode.HARD)],
            )
        absent = bool(options.get('absent'))
        if template == (
            event_checker.constants.TEMPLATE_NAMESPACE,
            event_constants.SORTIE_PREPARE_TEMPLATE,
        ):
            # absent 为真时 satisfied 表示"浮窗确实不在"，与出现时的语义相反。
            return SimpleNamespace(satisfied=(not overlay) if absent else overlay)
        return SimpleNamespace(satisfied=entry)

    def expect_ocr(_ctx: object, **options: object) -> SimpleNamespace:
        if options['roi'] is event_constants.MAP_NAME_ROI:
            if title is EventMode.HARD:
                texts = [f'{event_constants.MAP_NAME}（困难）']
            elif title is EventMode.NORMAL:
                texts = [event_constants.MAP_NAME]
            else:
                texts = ['无关标题']
            return SimpleNamespace(
                satisfied=title is not None, observation=[_detection(t) for t in texts]
            )
        return SimpleNamespace(
            satisfied=bool(titles), observation=[_detection(text) for text in titles]
        )

    monkeypatch.setattr(event_checker, 'load_ui_template', load_template)
    monkeypatch.setattr(event_checker, 'expect_template', expect_template)
    monkeypatch.setattr(event_checker, 'expect_ocr', expect_ocr)
    monkeypatch.setattr(event_checker, 'expect_template_center', lambda *_a, **_k: center)


def test_parse_stage_maps_identifiers_to_difficulty_and_node() -> None:
    """EX 全局编号与旧 E/H 写法都换算成难度与落点序号，越界与非法写法显式报错。"""
    supported = {
        'EX1': EventStage(difficulty=EventMode.NORMAL, node=1),
        'ex6': EventStage(difficulty=EventMode.NORMAL, node=6),
        'EX7': EventStage(difficulty=EventMode.HARD, node=1),
        'EX12': EventStage(difficulty=EventMode.HARD, node=6),
        'E3': EventStage(difficulty=EventMode.NORMAL, node=3),
        'H1': EventStage(difficulty=EventMode.HARD, node=1),
        'H6': EventStage(difficulty=EventMode.HARD, node=6),
    }
    for stage, expected in supported.items():
        assert parse_stage(stage) == expected

    for stage in ('EX13', 'EX0', 'E7', 'H0'):
        with pytest.raises(ValueError, match='章节标识超出范围'):
            parse_stage(stage)
    for stage in ('STAGE1', 'EX', 'E', '', '1'):
        with pytest.raises(ValueError, match='无效的章节标识'):
            parse_stage(stage)


@pytest.mark.parametrize(
    ('title_texts', 'node', 'hard', 'expected'),
    [
        (['EX1 天降火雨'], 1, False, True),
        (['EX7 天降火雨'], 1, True, False),
        (['EX1 天降火雨'], 1, True, False),
        (['EX7 困难 天降火雨'], 1, True, True),
        (['天降火雨'], 1, False, True),
        (['EX2 鹰群出击'], 1, False, False),
        (['〓EX1〓 天降火雨'], 1, False, True),
        ([], 1, False, False),
    ],
)
def test_is_stage_title_matched(
    title_texts: list[str],
    node: int,
    hard: bool,
    expected: bool,
) -> None:
    """标题需模式一致，且编号或章节名任一命中。"""
    assert is_stage_title_matched(title_texts, node=node, hard=hard) is expected


def test_recognition_probes_read_button_title_overlay_and_centers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮与标题各自取识别结果；浮窗模板失效时用关卡标题补强；两个中心各用自己模板。"""
    for button in (EventMode.NORMAL, EventMode.HARD, None):
        _install(monkeypatch, button=button)
        assert read_mode_button(object()) is button

    for title in (EventMode.HARD, EventMode.NORMAL, None):
        _install(monkeypatch, title=title)
        assert read_map_title(object()) is title

    _install(monkeypatch, titles=('EX1 天降火雨', '无关文字', 'EX7'))
    assert read_stage_title_texts(object()) == ['EX1 天降火雨', 'EX7']

    _install(monkeypatch, overlay=True)
    assert read_sortie_overlay(object()) is True
    _install(monkeypatch, overlay=False, titles=('EX1 天降火雨',))
    assert read_sortie_overlay(object()) is True
    _install(monkeypatch, overlay=False)
    assert read_sortie_overlay(object()) is False
    assert read_sortie_overlay(object(), absent=True) is True

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        event_checker, 'load_ui_template', lambda namespace, filename: (namespace, filename)
    )

    def center(_ctx: object, **options: object) -> tuple[float, float]:
        calls.append(options)
        return (0.25, 0.75)

    monkeypatch.setattr(event_checker, 'expect_template_center', center)

    assert read_mode_button_center(object()) == (0.25, 0.75)
    assert calls[0]['template'] == (
        (event_checker.constants.TEMPLATE_NAMESPACE, event_constants.MODE_NORMAL_TEMPLATE),
        (event_checker.constants.TEMPLATE_NAMESPACE, event_constants.MODE_HARD_TEMPLATE),
    )
    assert calls[0]['roi'] is event_constants.MODE_ROI

    assert read_sortie_prepare_center(object()) == (0.25, 0.75)
    assert calls[1]['template'] == (
        event_checker.constants.TEMPLATE_NAMESPACE,
        event_constants.SORTIE_PREPARE_TEMPLATE,
    )
    assert calls[1]['roi'] is event_constants.SORTIE_PREPARE_ROI


def test_check_event_map_page_accepts_button_or_plain_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模式按钮或「普通标题 + 无浮窗」任一成立即为活动地图页；给错活动玩法直接报错。"""
    cases = [
        (EventMode.NORMAL, None, False, False, True),
        (EventMode.HARD, None, False, False, True),
        (None, EventMode.NORMAL, False, False, True),
        (None, EventMode.HARD, False, False, False),
        (None, None, True, False, False),
        (EventMode.NORMAL, None, False, True, False),
        (None, None, False, True, True),
    ]
    for button, title, overlay, absent, expected in cases:
        _install(monkeypatch, button=button, title=title, overlay=overlay)
        assert check_event_map_page(object(), absent=absent) is expected

    _install(monkeypatch, button=EventMode.NORMAL)
    assert check_event_map_page(object(), event_type=event_constants.ACTIVITY) is True
    with pytest.raises(ValueError, match='当前 checker 不支持的活动玩法'):
        check_event_map_page(object(), event_type='other')


def test_read_event_map_state_derives_mode_only_from_clean_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """按钮与标题互为反向证据时才下难度结论；浮窗态不下难度结论。"""
    for button_mode, title_mode, expected in (
        (EventMode.NORMAL, EventMode.HARD, EventMode.HARD),
        (EventMode.HARD, EventMode.NORMAL, EventMode.NORMAL),
        (None, EventMode.NORMAL, EventMode.NORMAL),
        (None, None, None),
        (EventMode.NORMAL, EventMode.NORMAL, None),
        (EventMode.HARD, EventMode.HARD, None),
    ):
        assert calculate_current_mode(button_mode, title_mode) is expected

    for button, title, overlay, on_clean_map, current_mode in (
        (EventMode.NORMAL, EventMode.NORMAL, False, True, None),
        (EventMode.NORMAL, EventMode.HARD, False, True, EventMode.HARD),
        (EventMode.HARD, EventMode.NORMAL, False, True, EventMode.NORMAL),
        (None, EventMode.NORMAL, False, True, EventMode.NORMAL),
        (None, None, False, True, None),
        (EventMode.NORMAL, EventMode.HARD, True, False, None),
    ):
        _install(monkeypatch, button=button, title=title, overlay=overlay)
        assert read_event_map_state(object()) == EventMapState(
            on_clean_map=on_clean_map,
            button_mode=button,
            title_mode=title,
            current_mode=current_mode,
        )


def test_wait_event_mode_retries_until_target_or_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重读直到读到目标难度即成功，始终不符时按尝试次数放弃。"""
    states = [
        SimpleNamespace(current_mode=EventMode.NORMAL),
        SimpleNamespace(current_mode=EventMode.HARD),
    ]
    monkeypatch.setattr(event_checker, 'read_event_map_state', lambda *_a, **_k: states.pop(0))

    assert (
        wait_event_mode(
            object(),
            event_type=event_constants.ACTIVITY,
            mode=EventMode.HARD,
            attempts=3,
            interval_seconds=0.1,
        )
        is True
    )

    calls: list[object] = []

    def read_state(*_args: object, **_options: object) -> SimpleNamespace:
        calls.append(object())
        return SimpleNamespace(current_mode=EventMode.NORMAL)

    monkeypatch.setattr(event_checker, 'read_event_map_state', read_state)

    assert (
        wait_event_mode(
            object(),
            event_type=event_constants.ACTIVITY,
            mode=EventMode.HARD,
            attempts=2,
            interval_seconds=0.1,
        )
        is False
    )
    assert len(calls) == 2


def test_check_event_sortie_prepare_checks_overlay_then_stage_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """浮窗先判定，给出章节时再用标题核对难度与节点；章节越界在识别前报错。"""
    for stage, overlay, titles, absent, expected in (
        (None, True, (), False, True),
        ('EX7', True, ('EX7 困难 天降火雨',), False, True),
        ('EX1', True, ('EX7 困难 天降火雨',), False, False),
        ('EX1', False, (), False, False),
        ('EX1', False, (), True, True),
    ):
        _install(monkeypatch, overlay=overlay, titles=titles)
        assert check_event_sortie_prepare(object(), stage=stage, absent=absent) is expected

    _install(monkeypatch, overlay=True)
    with pytest.raises(ValueError, match='章节标识超出范围'):
        check_event_sortie_prepare(object(), stage='EX99')


def test_check_event_entry_and_task_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    """入口卡片可见性取模板命中，任务绑定事实直接透传，缺绑定时报导航错误。"""
    _install(monkeypatch, entry=True)
    assert check_event_entry(object(), event_type=event_constants.ACTIVITY) is True
    _install(monkeypatch, entry=False)
    assert check_event_entry(object(), event_type=event_constants.ACTIVITY) is False
    with pytest.raises(ValueError, match='当前 checker 不支持的活动玩法'):
        check_event_entry(object(), event_type='other')

    bound = SimpleNamespace(read_event_type=lambda: 'stage_push', read_event_stage=lambda: 'EX7')
    unbound = SimpleNamespace(read_event_type=lambda: None, read_event_stage=lambda: None)
    assert read_event_type(bound) == 'stage_push'
    assert read_event_stage(bound) == 'EX7'
    with pytest.raises(NavigationError, match='活动导航需要任务绑定 event_type'):
        read_event_type(unbound)
    with pytest.raises(NavigationError, match='活动导航需要任务绑定 event_stage'):
        read_event_stage(unbound)
