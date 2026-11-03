"""模块功能：换船动作实现层，每个文件只做一件事。

上层调用：
- fleet_select.models：读快照、切队、补齐成员、清空、拖拽排序。

下层依赖：
- application.controller：页面识别入口与页面点击动作。
- fleet_select.rules：OCR 后处理、约束判定与编队算法。

边界：只把算法给出的动作落到页面上，不判断编队是否合格、不决定换哪些槽位。
"""

__all__: list[str] = []
