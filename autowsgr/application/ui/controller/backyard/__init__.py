"""模块功能：组织后院主页面、浴室和食堂页面控制器。

上层调用：
- application.navigation：通过后院页面域执行页面导航。
- business.logistics：调用浴室和食堂页面的业务操作入口。

下层依赖：
- backyard.main_page：提供后院主页面导航控制器。
- backyard.bath_page：提供浴室页面控制器和修理识别规则。
- backyard.canteen_page：提供食堂页面控制器。

本包只划分后院页面域，不聚合导入子页面，避免跨页面导航形成导入副作用。
"""
