"""模块功能：换船的规则层，包含数据、后处理、算法与约束判定。

上层调用：
- fleet_select.models：算法结论与 OCR 后处理结果。
- fleet_select.operation：船卡判定、槽位定位与补船顺序。

下层依赖：
- fleet_select.types：规则、快照与槽位数据契约。
- resources/data/shipnames.yaml：标准舰名表。

边界：只做纯计算与纯数据，不读图、不点击、不访问设备。

各文件分工：shipnames 持有舰名资产，ocr 把识别原文变成事实，
planner 是编队核心算法，constraints 判断规则是否满足。
"""

__all__: list[str] = []
