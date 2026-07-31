import os
import re
import time
from typing import Any

from autowsgr.constants.custom_exceptions import ImageNotFoundErr
from autowsgr.constants.image_templates import IMG
from autowsgr.timer import Timer
from autowsgr.utils.io import yaml_to_dict
from autowsgr.utils.math_functions import cal_dis


# 入口标识映射: 内部用 a/b, 地图文件名用希腊字母 α/β (仅活动地图有 α/β 入口概念)
ENTRANCE_TO_GREEK = {'a': 'α', 'b': 'β'}
GREEK_TO_ENTRANCE = {'α': 'a', 'β': 'b'}


def parse_map_value(map_value) -> tuple[int, str | None]:
    """解析活动 plan 中的 map 字段, 返回 (map_id, entrance)。
    纯数字(1 或 '1')  -> (1, None)     # 无入口(如旧活动 E-1)
    '1a' / '1A'       -> (1, 'a')      # α 入口
    '3b' / '3B'       -> (3, 'b')      # β 入口
    """
    m = re.fullmatch(r'(\d+)([abAB])?', str(map_value).strip())
    if not m:
        raise ValueError(f'无法解析 map 值: {map_value!r}, 应为数字或 数字+a/b (如 1、1a、3b)')
    entrance = m.group(2).lower() if m.group(2) else None
    return int(m.group(1)), entrance


class Event:
    MAP_NAME_PREFIX: str | None = None  # 新活动子类覆盖为中文名前缀, 如 '激斗漩涡'

    def __init__(self, timer: Timer, event_name: str) -> None:
        self.timer = timer
        self.logger = timer.logger

        self.event_image = IMG.event[event_name]
        self.common_image = IMG.event['common']
        self.enemy_image = IMG.event['enemy']

        self.common_image['monster'] = [
            self.common_image.little_monster,
            self.common_image.big_monster,
        ]

    def _go_map_page(self):
        self.timer.go_main_page()
        self.timer.click(849, 261)

    def get_difficulty(self):
        """获取难度信息
        Returns:
            简单 0,困难 1
        这里同时有检查 _go_map_page 是否成功的功能
        如果未能检测到难度图标，但是检测到进入活动地图，默认没有通过简单难度，返回简单 0.
        """
        res = self.timer.wait_images(self.common_image.hard + self.common_image.easy)
        if res is None:
            self.logger.warning('ImageNotFoundErr: difficulty image not found')
            if self.timer.wait_image(self.event_image[2]):
                self.logger.info(
                    '成功进入活动页面，未检测到切换难度图标，请检查是否通关简单难度',
                )
                return 0
            self.timer.log_screen()
            raise ImageNotFoundErr

        if self.timer.image_exist(self.common_image.hard, need_screen_shot=False):
            return 0
        return 1

    def change_difficulty(self, chapter, retry=True) -> Any | None:
        r_difficulty = int(chapter in 'Hh')
        difficulty = self.get_difficulty()

        if r_difficulty != difficulty:
            time.sleep(0.2)
            if int(chapter in 'Hh'):
                if not self.timer.click_image(self.common_image.hard):
                    self.logger.error('请检查是否通关简单难度')
                    raise ImageNotFoundErr
            else:
                self.timer.click_image(self.common_image.easy)

            if self.get_difficulty() != r_difficulty:
                if retry:
                    return self.change_difficulty(chapter, False)
                self.timer.log_screen()
                raise ImageNotFoundErr
        return None

    def load_point_positions(self, map_path):
        """加载活动地图节点位置文件(覆盖 NormalFightInfo 的实现)。
        命名格式:
          - MAP_NAME_PREFIX 为 None: 旧活动命名 {chapter}-{map}.yaml, 如 E-1.yaml
          - 设置 MAP_NAME_PREFIX: 中文命名 {prefix}{H?}-Ex-{map}-{α|β}.yaml, 如 激斗漩涡-Ex-1-α.yaml
        """
        map_id, entrance = parse_map_value(self.map)
        self.map_id = map_id  # 供 plan 的 NODE_POSITION / _is_alpha 使用
        self.entrance = entrance
        if self.MAP_NAME_PREFIX is None:
            self.point_positions = yaml_to_dict(
                os.path.join(map_path, f'{self.chapter}-{map_id}.yaml'),
            )
            return
        prefix = self.MAP_NAME_PREFIX
        if str(self.chapter) in 'Hh':  # 困难难度前缀加 H
            prefix += 'H'
        if entrance is None:
            raise ValueError(
                f'新活动地图 {prefix}-Ex-{map_id} 需指定入口(map 写如 {map_id}a/{map_id}b)',
            )
        greek = ENTRANCE_TO_GREEK[entrance]
        fname = f'{prefix}-Ex-{map_id}-{greek}.yaml'
        self.point_positions = yaml_to_dict(os.path.join(map_path, fname))


class PatrollingEvent(Event):
    """巡戈作战活动 类"""

    def __init__(self, timer: Timer, event_name, map_positions) -> None:
        """
        Args:
            map_positions : 从主页面点进活动后, 去到对应地图需要点的位置
                : 对于 E1~E3/H1~H3, 值为地图页面滑到最左边时的点击位置
                : 对于 E4~E6/H4~H6, 值为地图页面滑到最右边时点击的位置
                : map_positions[0] 为 None
                : map_positions[1] 为 E1 的点击位置
                : map_positions[2] 为 E2 的点击位置...
        """
        self.MAP_POSITIONS = map_positions
        super().__init__(timer, event_name)

    def enter_map(self, chapter, map):
        """从活动地图选择界面进入到巡游地图"""
        assert chapter in 'HEhe'
        assert map in range(1, 7)
        self.change_difficulty(chapter)
        if map <= 3:
            self.timer.swipe(100, 300, 600, 300, duration=0.4, delay=0.15)
            self.timer.swipe(100, 300, 600, 300, duration=0.4, delay=0.15)
        else:
            self.timer.swipe(600, 300, 100, 300, duration=0.4, delay=0.15)
            self.timer.swipe(600, 300, 100, 300, duration=0.4, delay=0.15)
        self.timer.click(*self.MAP_POSITIONS[map], delay=0.25)
        assert self.timer.wait_image(self.event_image[2]) is not False  # 是否成功进入地图

    def go_fight_prepare_page(self):
        self.timer.click(789, 455)
        assert self.timer.wait_image(IMG.identify_images['fight_prepare_page']) is not False

    def random_walk(self):
        """随机游走,寻找敌人"""
        ways = ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))
        import random

        way = random.choice(ways)
        position = (480, 270)
        step = (320, 180)
        end = (position[0] + step[0] * way[0], position[1] + step[1] * way[1])
        self.timer.click(*end, delay=3)
        if self.timer.image_exist(self.event_image[1]):
            self.timer.click(911, 37)
        if self.timer.image_exist(self.event_image[3]):
            self.timer.click(30, 50)

    def get_close(self, images):
        while True:
            ret = self.timer.wait_images_position(
                images,
                confidence=0.8,
                gap=0.03,
                timeout=1,
            )
            if cal_dis([ret[0]], [480]) ** 0.5 < 320 and cal_dis([ret[1]], [270]) ** 0.5 < 180:
                return ret
            ret = (ret[0] - 130, ret[1]) if ret[0] > 480 else (ret[0] + 130, ret[1])
            self.timer.click(*ret)

    def find(self, images, max_times=20):
        for _ in range(max_times):
            ret = self.timer.wait_images_position(
                images,
                confidence=0.75,
                gap=0.03,
                timeout=1,
            )
            if ret is not None:
                return ret
            self.random_walk()
        return None
