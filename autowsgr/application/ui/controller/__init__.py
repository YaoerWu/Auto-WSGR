"""模块功能：组织业务流程使用的 UI 页面控制器区域。

上层调用：
- application.runtime、application.navigation 和 business：按页面业务调用子包入口。

下层依赖：
- application.ui.controller.home、backyard、sidebar、operations 和 shared：提供页面及公共视觉控制器。

Each child package owns one page or page group. Fleet formation and shipyard
controllers live under ``autowsgr.application.ui.controller.fleet``. Device
access, OCR, image matching, waits, and calibration remain in
``autowsgr.common``.
"""
