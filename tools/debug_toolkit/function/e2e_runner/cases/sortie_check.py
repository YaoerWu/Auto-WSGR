"""静态验证 case：用外挂截图跑出征页域探针。

样本属于临时验证数据，放在仓库之外的 debug 目录，不随仓库提交。
运行方式::

    python tools/debug_toolkit/main.py e2e --static sortie_check
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from autowsgr.application.controller.sortie import read_sortie_layer


if TYPE_CHECKING:
    from autowsgr.application.navigation.types import PageName


DESC = '出征页域探针静态验证: 一次读六模板判当前标签页'

# 外挂截图目录；样本是各标签激活时的整页截图。
_SHOT_DIR = Path('C:/ShiinaKuroko/01.Project/debug/nav/静态模板/出征')


def _samples() -> tuple[tuple[str, PageName], ...]:
    """按样本顺序返回 (文件名, 期望页面) 组合。"""
    from autowsgr.application.navigation.types import PageName

    return (
        ('出征页面.png', PageName.SORTIE_MAP),
        ('选择演习tab.png', PageName.EXERCISE),
        ('选择远征tab.png', PageName.EXPEDITION),
        ('选择战役tab.png', PageName.CAMPAIGN),
        ('选择决战tab.png', PageName.DECISIVE_BATTLE),
    )


def run(rt: Any) -> bool:
    """按样本切换静态截图并校验域探针判层结果。"""
    ctx = rt.ctx

    for filename, expected in _samples():
        rt.use_frame(_SHOT_DIR / filename)
        actual = rt.action(f'识别 {filename}', read_sortie_layer, ctx)
        if actual is rt.FAILED:
            return False
        if not rt.check(
            f'{filename} → {expected.value}',
            lambda _actual=actual, _expected=expected: _actual == (_expected,),
        ):
            return False
    return True
