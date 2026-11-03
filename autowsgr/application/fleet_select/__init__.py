"""模块功能：编排出征准备页的换船业务，对外只暴露一个换船入口。

上层调用：
- business：出征、活动、演习、决战、战役任务在准备舰队时调用 adjust_fleet。

下层依赖：
- application.controller：识别页面事实、执行点击。
- fleet_select.rules：舰名表、OCR 后处理、编队算法与约束判定。
- fleet_select.operation：读快照、选船、清空、拖拽与切队。
- fleet_select.models：三套换船模式的流程组装。

边界：只编排换船业务流程，不直接读取图像、不直接点击坐标。
具体页面的识别与点击能力归 application.controller。
"""

from autowsgr.application.fleet_select.service import adjust_fleet


__all__ = ['adjust_fleet']
