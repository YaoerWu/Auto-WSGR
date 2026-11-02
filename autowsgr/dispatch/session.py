"""模块功能：维护程序运行期内的会话状态。

上层调用：
- application.navigation.service：记录导航栈与区服选择标记。
- application.controller 与 registry：读写每日浮窗的处理标记。

下层依赖：
- common.system.enums：提供字符串枚举基类。

边界：只保存程序运行期内的状态，重启即消失；不保存任务级事实、不访问设备、不做业务判断。
"""

from __future__ import annotations

from datetime import date

from autowsgr.common.system.enums import StrEnum


class DailyPopup(StrEnum):
    """每日浮窗标识。

    三个每日浮窗彼此**解耦**：各自处理成功后记录自己的标记，各自的确认入口在读到
    自己的标记时跳过识别——处理过一个不影响另外两个。
    """

    NEWS = 'daily_news'
    REWARD = 'daily_reward'
    REWARD_CONFIRM = 'daily_reward_confirm'


class SessionState:
    """程序运行期内的导航会话状态。"""

    # 只保留最近若干层页面：更老的历史既不影响算路（只看栈顶），也回退不到，
    # 留着只会随运行时间无限增长。
    _MAX_PAGES = 8

    def __init__(self) -> None:
        self._server_selected = False
        self._popup_settled_on: dict[DailyPopup, date] = {}
        self._pages: list[str] = []

    @property
    def server_selected(self) -> bool:
        """本次程序运行是否已处理过区服选择。"""
        return self._server_selected

    def mark_server_selected(self) -> None:
        """标记本次运行已完成区服选择。"""
        self._server_selected = True

    def popup_settled(self, popup: DailyPopup) -> bool:
        """今天是否已经处理过某个每日浮窗。

        游戏每天第一次进主页会弹浮窗，处理过的当天不会再弹。标记带日期，
        跨过零点自动失效，第二天重新确认——不需要定时清除。
        """
        return self._popup_settled_on.get(popup) == date.today()  # noqa: DTZ011  # 本地墙上时钟

    def mark_popup_settled(self, popup: DailyPopup) -> None:
        """记下今天已经处理过某个每日浮窗。"""
        self._popup_settled_on[popup] = date.today()  # noqa: DTZ011  # 本地墙上时钟

    def current_page(self) -> str | None:
        """返回导航栈顶的页面值。"""
        return self._pages[-1] if self._pages else None

    def push_page(self, page: str) -> None:
        """把页面压入导航栈，只保留最近若干层。"""
        self._pages.append(page)
        del self._pages[: -self._MAX_PAGES]

    def pop_page(self) -> str | None:
        """弹出导航栈顶的页面值。"""
        return self._pages.pop() if self._pages else None

    def replace_page(self, page: str) -> None:
        """把栈顶换成另一个页面。

        同一个域里的页面共用一套画面框架，换来换去只认「当前是哪个页面」这一个
        事实，栈里不该留下一串已经不在画面上的旧标签页。
        """
        if self._pages:
            self._pages[-1] = page
        else:
            self._pages.append(page)

    def clear_pages(self) -> None:
        """清空导航栈；游戏被强杀重开后栈里的页面已经不存在。"""
        self._pages.clear()


_SESSION = SessionState()


def get_session() -> SessionState:
    """返回进程级会话状态。"""
    return _SESSION


__all__ = ['DailyPopup', 'SessionState', 'get_session']
