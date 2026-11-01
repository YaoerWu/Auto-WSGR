"""静态验证 case：用外挂截图跑出征准备页域探针。

四张样本分别是普通出征、决战、演习、战役的准备页，共用同一个识别 ROI。
运行方式::

    python tools/debug_toolkit/main.py e2e --static battle_preparation_check
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from autowsgr.application.ui.navigation.checker.sortie.battle_preparation import (
    read_battle_preparation_layer,
)


if TYPE_CHECKING:
    from autowsgr.application.ui.navigation.types import PageName


DESC = '出征准备页域探针静态验证: 普通 / 决战 / 演习 / 战役四页共用 ROI'

# 外挂截图目录；样本是四类准备页的整页截图。
_SHOT_DIR = Path('C:/ShiinaKuroko/01.Project/debug/nav/静态模板/出征页')


def _samples() -> tuple[tuple[str, PageName], ...]:
    """按样本顺序返回 (文件名, 期望页面) 组合。"""
    from autowsgr.application.ui.navigation.types import PageName

    return (
        ('普通出征-出征准备.png', PageName.BATTLE_PREPARATION),
        ('决战-出征准备.png', PageName.DECISIVE_BATTLE_PREPARATION),
        ('演习-出征准备.png', PageName.EXERCISE_PREPARATION),
        ('战役-出征准备.png', PageName.CAMPAIGN_PREPARATION),
    )


def run(rt: Any) -> bool:
    """按样本切换静态截图并校验准备页判层结果。"""
    ctx = rt.ctx

    for filename, expected in _samples():
        rt.use_frame(_SHOT_DIR / filename)
        # 静态帧不变化，重试只会白等，判层只要一帧。
        actual = rt.action(f'识别 {filename}', read_battle_preparation_layer, ctx, attempts=1)
        if actual is rt.FAILED:
            return False
        if not rt.check(
            f'{filename} → {expected.value}',
            lambda _actual=actual, _expected=expected: _actual == (_expected,),
        ):
            return False
    return True
