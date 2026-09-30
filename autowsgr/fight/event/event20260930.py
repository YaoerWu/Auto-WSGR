import os

from autowsgr.constants.data_roots import MAP_ROOT
from autowsgr.fight.event.event import Event, parse_map_value
from autowsgr.fight.normal_fight import NormalFightInfo, NormalFightPlan
from autowsgr.timer import Timer


# 活动地图选择界面节点位置(相对坐标), 字母 A~F 即地图编号 1~6
NODE_POSITION = {
    'A': [0.08798017348203221, 0.2251655629139073],
    'B': [0.5947955390334573, 0.2240618101545254],
    'C': [0.7856257744733581, 0.20750551876379691],
    'D': [0.19640644361833953, 0.5242825607064018],
    'E': [0.47026022304832715, 0.6401766004415012],
    'F': [0.7806691449814126, 0.7483443708609272],
}
# 补充数字键(1~6 对应 A~F), 使 NODE_POSITION[map_id] 可直接索引
NODE_POSITION |= {ord(k) - ord('A') + 1: v for k, v in NODE_POSITION.items()}


class EventFightPlan(Event, NormalFightPlan):
    def __init__(
        self,
        timer: Timer,
        plan_path,
        auto_answer_question=False,
        from_alpha=None,
        fleet_id=None,
        event='20260930',
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
        map_entrance = parse_map_value(self.config.map)[1]
        if from_alpha is not None:
            self.from_alpha = from_alpha
        elif map_entrance is not None:
            self.from_alpha = map_entrance == 'a'  # a=α→True, b=β→False
        else:
            self.from_alpha = self.config.from_alpha

    def _load_fight_info(self):
        self.info = EventFightInfo20260930(self.timer, self.config.chapter, self.config.map)
        self.info.load_point_positions(os.path.join(MAP_ROOT, 'event', self.event_name))

    def _change_fight_map(self, chapter_id, map_id):
        """选择并进入战斗地图(chapter-map)"""
        self.change_difficulty(chapter_id)

    def _go_map_page(self):
        self.timer.go_main_page()
        self.timer.click_image(self.event_image[5], timeout=10)
        if self.timer.wait_image(self.event_image[6], timeout=2):
            self.timer.relative_click(0.618, 0.564)
            self._go_map_page()

    def _is_alpha(self):
        # 像素检测当前入口: α 入口按钮高亮为橙色(RGB (37, 146, 249) 的 BGR 表示)
        return self.timer.check_pixel(
            (794, 312),
            (249, 146, 37),
            screen_shot=True,
        )  # 蓝 绿 红

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

        # 选择入口: 地图标明 α/β 入口(map 带 a/b)时才检测切换; 未标明则自动跳过
        entrance = parse_map_value(self.config.map)[1]
        if entrance is not None and self._is_alpha() != self.from_alpha:
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


class EventFightInfo20260930(Event, NormalFightInfo):
    def __init__(self, timer: Timer, chapter_id, map_id, event='20260930') -> None:
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
