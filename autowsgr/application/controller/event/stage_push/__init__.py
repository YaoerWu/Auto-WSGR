"""模块功能：提供普通推图活动 checker 的模块入口。

上层调用：
- application.controller.event：导出本活动 checker。
- application.ui.navigation：按活动玩法调用本 checker 的页面识别入口。

下层依赖：
- event.stage_push.checker：提供页面识别入口与页面事实模型。

本模块只导出稳定入口与事实模型，不放业务实现。
"""

from autowsgr.application.controller.event.stage_push.checker import (
    EventMapState,
    EventMode,
    EventStage,
    check_event_entry,
    check_event_map_page,
    check_event_sortie_prepare,
    parse_stage,
    read_event_map_state,
    read_event_stage,
    read_event_type,
    read_mode_button_center,
    read_sortie_prepare_center,
    wait_event_mode,
)


__all__ = [
    'EventMapState',
    'EventMode',
    'EventStage',
    'check_event_entry',
    'check_event_map_page',
    'check_event_sortie_prepare',
    'parse_stage',
    'read_event_map_state',
    'read_event_stage',
    'read_event_type',
    'read_mode_button_center',
    'read_sortie_prepare_center',
    'wait_event_mode',
]
