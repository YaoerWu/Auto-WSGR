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
    # 混入宿主类(如 NormalFightInfo)时由宿主提供的属性
    chapter: str | int
    map: str | int
    point_positions: dict | None

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
        # 活动页面标志(event_image[2], 如标题横幅), 需与难度图标同帧检测
        ACTIVITY_PAGE_CONFIDENCE = 0.85
        # 在活动页面且没有任何难度图标(无难度切换 UI 的活动)时, 才视为简单难度
        _ = self.timer.wait_image(
            self.event_image[2],
            confidence=ACTIVITY_PAGE_CONFIDENCE,
        )
        if not self.timer.image_exist(
            self.common_image.hard + self.common_image.easy,
            need_screen_shot=False,
        ):
            self.logger.info(
                '成功进入活动页面，未检测到切换难度图标，默认为通关简单难度',
            )
            return 0

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
        按 '-' 分割地图文件名匹配, 不依赖活动中文名前缀, 兼容多种命名:
          - 旧活动: {chapter}-{map}.yaml, 如 E-1.yaml
          - 新活动: {名}{H?}-Ex-{map}-{α|β?}.yaml, 如 激斗漩涡-Ex-1-α.yaml, 最强之舟-Ex-1.yaml
            前缀段以 H 结尾表示困难难度; α/β 段可选, 文件带入口时须与 plan 的 map 一致
            连续编号的活动(如 最强之舟-Ex-1 ~ Ex-12)没有 H 前缀文件, H1~H6 对应 Ex-{map+6}(即 E7~E12)
        """
        map_id, entrance = parse_map_value(self.map)
        self.map_id = map_id  # 供 plan 的 NODE_POSITION / _is_alpha 使用
        self.entrance = entrance
        hard = str(self.chapter) in 'Hh'

        # 旧活动命名直接构造
        legacy = os.path.join(map_path, f'{self.chapter}-{map_id}.yaml')
        if os.path.exists(legacy):
            self.point_positions = yaml_to_dict(legacy)
            return

        def find_map_file(number, want_hard):
            """查找编号为 number、难度匹配的 Ex 地图文件, 返回完整路径或 None"""
            for fname in sorted(os.listdir(map_path)):
                if not fname.endswith('.yaml'):
                    continue
                parts = fname.removesuffix('.yaml').split('-')
                if 'Ex' not in parts:
                    continue
                i = parts.index('Ex')
                if i + 1 >= len(parts) or parts[i + 1] != str(number):
                    continue
                # 入口: 文件名带 α/β 时须与 plan 一致, 不带则任意入口均可
                if len(parts) > i + 2 and GREEK_TO_ENTRANCE.get(parts[i + 2]) != entrance:
                    continue
                if parts[0].endswith('H') != want_hard:
                    continue
                return os.path.join(map_path, fname)
            return None

        map_file = find_map_file(map_id, hard)
        if map_file is None and hard:
            # 无 H 前缀文件的连续编号活动: H1~H6 对应 Ex-{map+6}
            map_file = find_map_file(map_id + 6, False)
        if map_file is None:
            raise FileNotFoundError(
                f'在 {map_path} 未找到地图 {self.map!r}(chapter={self.chapter}) 的节点位置文件; '
                f'若活动有 α/β 入口, plan 的 map 需写如 {map_id}a/{map_id}b',
            )
        self.point_positions = yaml_to_dict(map_file)


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
