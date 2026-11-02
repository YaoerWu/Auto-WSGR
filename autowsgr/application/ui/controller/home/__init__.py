"""模块功能：导出 home 区域下的主页和活动页面 Controller。

上层调用：
- application.navigation：取得主页和活动页面的稳定入口。
- application.runtime：识别主页并处理启动浮层。
- business：执行主页和活动页面业务流程。

下层依赖：
- application.ui.controller.home.main_page：提供主页 Controller。
- application.ui.controller.home.event_page：提供活动地图 Controller。

本模块只负责区域级稳定导出，不执行页面注册、设备操作或导航动作。
"""

__all__: list[str] = []
