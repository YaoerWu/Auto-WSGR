"""20260730 激斗漩涡 活动脚本

地图文件采用中文活动名 + 希腊字母入口的命名:
  激斗漩涡-Ex-{n}-{α|β}.yaml    (简单难度, chapter=E)
  激斗漩涡H-Ex-{n}-{α|β}.yaml   (困难难度, chapter=H)
plan 中用 `map: {n}a` / `map: {n}b` 指定地图号与入口(a=α, b=β), chapter 仍为 E/H。
入口(α/β)绑定在地图文件名上, 因此 _is_alpha 改为根据地图名判断, 不再做像素检测。

注意: NODE_POSITION 坐标、_go_map_page 进入逻辑、event_image 引用依赖实机截图,
      需确认后填入(见 TODO)。还需在 autowsgr/data/images/event/20260730/ 放置 1.PNG…N.PNG。
"""

import os

from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.fight.event.event import Event
from autowsgr.fight.normal_fight import NormalFightInfo, NormalFightPlan
from autowsgr.timer import Timer


NODE_POSITION = (
    None,
    (0.17708333333333334, 0.3148148148148148),
    (0.17395833333333333, 0.725925925925926),
    (0.5010416666666667, 0.29814814814814816),
    (0.490625, 0.7462962962962963),
    (0.8135416666666667, 0.29444444444444445),
    (0.8125, 0.7462962962962963),
)


class EventFightPlan(Event, NormalFightPlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        auto_answer_question=False,
        from_alpha=None,
        fleet_id=None,
        event='20260730',
    ) -> None:
        """Args:
        fleet_id : 新的舰队参数, 优先级高于 plan 文件, 如果为 None 则使用计划参数.

        from_alpha : 指定入口, True=α入口, False=β入口。
            本活动入口绑定在地图名上(map 字段的 a/b), 默认从地图名推导;
            显式传入时优先级最高。
        """
        if os.path.isabs(plan_path):
            plan_path = plan_path
        else:
            plan_path = timer.plan_tree['event'][event][plan_path]

        self.event_name = event
        self.auto_answer_question = auto_answer_question
        NormalFightPlan.__init__(self, timer, plan_path, fleet_id=fleet_id)
        Event.__init__(self, timer, event)

        # 入口优先级: 显式入参 > 地图名(a/b) > plan 文件 from_alpha
        if from_alpha is not None:
            self.from_alpha = from_alpha
        elif self.info.entrance is not None:
            self.from_alpha = self.info.entrance == 'a'  # a=α→True, b=β→False
        else:
            self.from_alpha = self.config.from_alpha

    def _load_fight_info(self):
        self.info = EventFightInfo20260730(self.timer, self.config.chapter, self.config.map)
        self.info.load_point_positions(os.path.join(MAP_ROOT, 'event', self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _go_map_page(self):
        # TODO: 根据 20260730 实机界面确认进入活动地图的点击逻辑与 event_image 引用
        self.timer.go_main_page()
        self.timer.click_image(self.event_image[5], timeout=10)
        if self.timer.wait_image(self.event_image[6], timeout=2):
            self.timer.relative_click(0.618, 0.564)
            self._go_map_page()

    def _is_alpha(self):
        # 根据所选地图名(plan 中 map 的 a/b 入口)判断当前入口。
        # 新活动入口绑定在地图文件名上, 无需像素检测。
        # 若实机发现进入地图后仍需切换入口, 请改回屏幕检测(如 check_pixel)。
        return self.info.entrance == 'a'

    def _go_fight_prepare_page(self) -> None:
        if self.timer.image_exist(
            self.info.event_image[3],
            need_screen_shot=0,
        ):  # 每日答题界面
            if self.auto_answer_question:
                pass  # TODO: 自动答题逻辑未实现
            else:
                self.timer.click_image(
                    self.event_image[4],
                    timeout=3,
                )  # 点击取消每日答题按钮

        if not self.timer.image_exist(self.info.event_image[1]):
            self.timer.relative_click(*NODE_POSITION[self.info.map_id])

        # 选择入口: _is_alpha 根据地图名, 与 from_alpha(同样来自地图名)一致时无需切换
        if self._is_alpha() != self.from_alpha:
            entrance_position = [(797, 369), (795, 317)]
            self.timer.click(*entrance_position[int(self.from_alpha)])

        if not self.timer.click_image(self.event_image[1], timeout=10):
            self.timer.logger.warning('进入战斗准备页面失败,重新尝试进入战斗准备页面')
            self.timer.relative_click(*NODE_POSITION[self.info.map_id])
            self.timer.click_image(self.event_image[1], timeout=10)

        try:
            self.timer.wait_pages('fight_prepare_page', after_wait=0.15)
        except Exception as e:
            self.timer.logger.warning(f'匹配fight_prepare_page失败，尝试重新匹配, error: {e}')
            self.timer.go_main_page()
            self._go_map_page()
            self._go_fight_prepare_page()


class EventFightInfo20260730(Event, NormalFightInfo):
    # 活动地图中文命名前缀; 简单难度用 '激斗漩涡', 困难难度由 load_point_positions 自动追加 'H'
    MAP_NAME_PREFIX = '激斗漩涡'

    def __init__(self, timer: Timer, chapter_id, map_id, event='20260730') -> None:
        NormalFightInfo.__init__(self, timer, chapter_id, map_id)
        Event.__init__(self, timer, event)
        self.map_image = (
            self.common_image['easy']
            + self.common_image['hard']
            + [self.event_image[1]]
            + [self.event_image[2]]
        )
        self.end_page = 'unknown_page'
        self.state2image['map_page'] = [self.map_image, 5]
