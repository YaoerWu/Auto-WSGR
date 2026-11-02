"""模块功能：提供活动 checker 的公开出口。

上层调用：
- application.navigation：按活动类型调用对应 checker。

下层依赖：
- 各活动的 checker 子包：当前为普通推图 normal，后续玩法各自增加。

本模块只导出活动 checker，不放实现；一个活动一个子包，玩法之间的相似代码先各自保留。
"""

from autowsgr.application.controller.event import stage_push


__all__ = ['stage_push']
