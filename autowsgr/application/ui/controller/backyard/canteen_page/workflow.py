"""模块功能：暂存食堂的做菜流程，尚未迁移到新链路。

上层调用：
- 暂无。本模块是旧 page.py 里做菜流程的暂存位置，等第二阶段迁移到新链路后由 page.py 调用。

下层依赖：
- canteen_page.constants / canteen_page.operations：提供坐标与原子点击；
- common.vision 的旧 ImageChecker 与 application.vision.resources 的旧 Templates：
  提供做菜过程的模板识别；
- common.device.interaction：旧的页面到达等待。

边界：暂存代码，不接进导航器。它依赖的若干旧模块已随架构升级删除，
因此本模块当前无法导入；迁移到新链路后这些依赖会被换掉。
"""

from __future__ import annotations

import time

from autowsgr.application.ui.controller.backyard.canteen_page import constants, operations
from autowsgr.application.vision.resources import Templates
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import ImageChecker


_log = get_logger('ui.backyard.canteen_page')


# ── 做菜流程参数 ─────────────────────────────────────────────────────────────

_COOK_BUTTON_TIMEOUT_SECONDS = 7.5  # 等待做菜按钮出现的最长时间。
_COOK_BUTTON_POLL_INTERVAL_SECONDS = 0.3  # 轮询做菜按钮的间隔。
_COOK_TRANSITION_WAIT_SECONDS = 0.5  # 点击做菜或确认覆盖后的页面过渡时间。
_CANCEL_POPUP_WAIT_SECONDS = 0.3  # 取消覆盖后等待弹窗关闭的时间。


# ── 做菜流程 ────────────────────────────────────────────────────────────────


def cook(self, position: int = 1, *, force_cook: bool = False) -> bool:
    """选择菜谱并做菜。

    Args:
        position: 菜谱编号，范围为 1-3。
        force_cook: 有料理生效时是否继续覆盖做菜。

    Returns:
        做菜是否成功；没有次数或取消覆盖时返回 ``False``。

    Raises:
        TimeoutError: 做菜按钮在等待期限内未出现。
    """
    if position not in constants.RECIPE_POSITIONS:
        _log.error(
            '[UI] 食堂 → 拒绝做菜：菜谱位置={}，期望范围=1..3，结果=拒绝',
            position,
        )
        raise ValueError(f'菜谱编号必须为 1-3，收到: {position}')
    _log.info(
        '[UI] 食堂 → 做菜：菜谱位置={}，强制覆盖={!r}，状态=开始',
        position,
        force_cook,
    )
    # 1. 选择目标菜谱。
    operations.click_recipe(self._ctrl, constants.RECIPE_POSITIONS[position])

    # 2. 等待做菜按钮出现。
    deadline = time.monotonic() + _COOK_BUTTON_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        screen = self._ctrl.screenshot()
        detail = ImageChecker.find_template(screen, Templates.Cook.COOK_BUTTON)
        if detail is not None:
            operations.click_cook_button(self._ctrl, detail.center)
            break
        time.sleep(_COOK_BUTTON_POLL_INTERVAL_SECONDS)
    else:
        _log.error(
            '[UI] 食堂 → 做菜超时：菜谱位置={}，超时={:.1f}s，原因=做菜按钮未出现，结果=失败',
            position,
            _COOK_BUTTON_TIMEOUT_SECONDS,
        )
        raise TimeoutError(f'做菜按钮未出现 ({_COOK_BUTTON_TIMEOUT_SECONDS}s)')

    time.sleep(_COOK_TRANSITION_WAIT_SECONDS)

    # 3. 检测「效果正在生效」弹窗并决定覆盖或取消。
    screen = self._ctrl.screenshot()
    has_active_cook = ImageChecker.template_exists(screen, Templates.Cook.HAVE_COOK)
    _log.debug(
        '[UI] 食堂 → 判断覆盖：菜谱位置={}，强制覆盖={!r}，已有料理={!r}',
        position,
        force_cook,
        has_active_cook,
    )
    if has_active_cook:
        if force_cook:
            operations.click_force_cook(self._ctrl)
            time.sleep(_COOK_TRANSITION_WAIT_SECONDS)
            screen = self._ctrl.screenshot()
            no_times = ImageChecker.template_exists(screen, Templates.Cook.NO_TIMES)
            _log.debug('[UI] 食堂 → 判断次数：菜谱位置={}，次数不足={!r}', position, no_times)
            if no_times:
                operations.click_dismiss_popup(self._ctrl)
                _log.warning(
                    '[UI] 食堂 → 做菜失败：菜谱位置={}，强制覆盖={!r}，原因=次数不足，结果=失败',
                    position,
                    force_cook,
                )
                return False
        else:
            operations.click_cancel_cook(self._ctrl)
            time.sleep(_CANCEL_POPUP_WAIT_SECONDS)
            operations.click_dismiss_popup(self._ctrl)
            _log.info(
                '[UI] 食堂 → 取消做菜：菜谱位置={}，原因=已有料理，结果=已取消',
                position,
            )
            return False

    # 4. 跳过结果动画，完成做菜流程。
    operations.click_skip_animation(self._ctrl)
    _log.info(
        '[UI] 食堂 → 做菜：菜谱位置={}，强制覆盖={!r}，结果=已提交',
        position,
        force_cook,
    )

    return True
