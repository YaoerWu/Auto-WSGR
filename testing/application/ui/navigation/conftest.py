"""模块功能：导航器单测的共享替身。

直接调用方：testing/application/ui/navigation 下的各测试模块。

直接依赖：pytest、navigation 的注册表与 checker 模块。

边界：用替身接管设备点击与页面确认，不连接设备、不识别画面。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from autowsgr.application.controller import home, login, sidebar
from autowsgr.application.ui.navigation import executor as executor_module
from autowsgr.application.ui.navigation import registry
from autowsgr.application.ui.navigation.types import NavTab, PageName


if TYPE_CHECKING:
    from collections.abc import Callable


class _Ctrl:
    """设备服务替身，记录点击落点。"""

    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float, *, delay: bool = False) -> None:  # noqa: ARG002
        self.clicks.append((x, y))


@pytest.fixture
def ctx() -> Any:
    """带活动任务参数与「永不让路」断点的上下文替身。"""
    return SimpleNamespace(
        runtime=SimpleNamespace(ctrl=_Ctrl()),
        read_event_type=lambda: 'stage_push',
        read_event_stage=lambda: 'EX7',
        check_interrupt=lambda: None,
    )


@pytest.fixture
def accept_path(monkeypatch: pytest.MonkeyPatch) -> Callable[[PageName], None]:
    """返回「只让目标页的确认入口命中」的安装器。

    替身跟着 `absent` 翻转：后识别问的是「这一页还在不在」，从更深的层退回时
    出发页必须判为已经收起。链路上 `confirm=False` 的中间步不做到达确认，
    因此只需要最终目标命中。
    """

    def _install(target: PageName) -> None:
        for page in list(registry._PAGE_CHECKERS):
            matched = page is target
            monkeypatch.setitem(
                registry._PAGE_CHECKERS,
                page,
                lambda _ctx, *, absent=False, _m=matched, **_kwargs: _m != absent,
            )
        # 域探针不经过逐页注册表：目标在域里时让它报出目标这一层，否则当作没命中。
        if registry.is_domain_page(target):
            monkeypatch.setattr(
                registry,
                '_DOMAIN_PROBERS',
                (lambda _ctx, **_options: (target,),),
            )
        else:
            monkeypatch.setattr(registry, '_DOMAIN_PROBERS', (lambda _ctx, **_options: (),))
        monkeypatch.setattr(
            home,
            'read_news_overlay',
            lambda _ctx: SimpleNamespace(matched=False, checked=None),
        )
        monkeypatch.setattr(home, 'check_home_reward_overlay', lambda _ctx: False)
        # 勾选反馈默认当作成功，避免替身触发真实截图。
        monkeypatch.setattr(home, 'check_news_checked', lambda _ctx, **_: True)
        monkeypatch.setattr(home, 'check_home_reward_confirm', lambda _ctx: False)
        # 浮窗链收尾要判断「是不是已经停在侧边栏」，替身一律当作不在，走点击那条路。
        monkeypatch.setattr(sidebar, 'check_sidebar_page', lambda _ctx, **_options: False)
        # 「首页 → 出征页」会切回出征标签。标签项是 frozen dataclass，注册时已绑定
        # checker 引用，因此整项替换而不是改模块属性；点击保留真实现（它只点击、
        # 不识别），只把 checker 换成替身；稳定等待在单测里没有意义。
        sortie_tab = registry.get_tabs(PageName.SORTIE_MAP)['sortie']
        monkeypatch.setitem(
            registry._TABS[PageName.SORTIE_MAP],
            'sortie',
            NavTab(sortie_tab.click, lambda _ctx, **_options: True, '出征'),
        )
        monkeypatch.setattr(executor_module.time, 'sleep', lambda _seconds: None)
        # 换区入口先识别中心、识别不到才退回固定落点；替身统一走兜底。
        monkeypatch.setattr(login, 'read_switch_entry_center', lambda _ctx: None)
        monkeypatch.setattr(login, 'read_enter_button_center', lambda _ctx: None)

    return _install
