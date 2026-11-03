"""模块功能：三套换船模式的流程组装。

上层调用：
- fleet_select.service：按换船模式选一套组装。

下层依赖：
- fleet_select.rules：规则归一化、编队算法与 OCR 后处理。
- fleet_select.operation：读快照、选船、清空、拖拽与切队。

边界：只组装流程，不定义规则数据，不直接调用页面类。
"""

__all__: list[str] = []
