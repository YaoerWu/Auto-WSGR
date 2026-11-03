"""模块功能：战术支援按钮与浮窗的公开出口，只汇总识别入口与点击控制器。

上层调用：
- 战术支援业务编排：先识别按钮与浮窗状态，再决定点哪一下。

下层依赖：
- application.controller.sortie.battle_preparation.tactical_support.checker：页面事实识别。
- application.controller.sortie.battle_preparation.tactical_support.page：单次点击。

边界：不含开启策略与流程编排，那部分归业务层。
"""

from __future__ import annotations

from autowsgr.application.controller.sortie.battle_preparation.tactical_support.checker import (
    TacticalSupportState,
    read_tactical_support,
    read_tactical_support_button_center,
)
from autowsgr.application.controller.sortie.battle_preparation.tactical_support.page import (
    TacticalSupportPage,
)


__all__ = [
    'TacticalSupportPage',
    'TacticalSupportState',
    'read_tactical_support',
    'read_tactical_support_button_center',
]
