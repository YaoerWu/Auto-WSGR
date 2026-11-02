"""模块功能：编排出征准备页的换船业务。

上层调用：
- business：在出征、活动、演习等任务里准备舰队。

下层依赖：
- application.controller：识别页面事实、执行点击。
- application.fleet_select.names：舰名表与同船身份归一化。

边界：只编排换船业务流程，不直接读取图像、不直接点击坐标。
具体页面的识别与点击能力归 application.controller。
"""

__all__: list[str] = []
