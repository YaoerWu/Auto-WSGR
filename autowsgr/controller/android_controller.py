import threading as th
import time

from airtest.core.android.android import Android

from autowsgr.utils.api_image import absolute_to_relative, relative_to_absolute


class AndroidController:
    """安卓控制器

    用于提供底层的控制接口
    """

    def __init__(self, config, logger, dev: Android) -> None:
        self.config = config
        self.logger = logger
        self.dev = dev
        self.resolution = self.snapshot().shape[:2]
        self.resolution = self.resolution[::-1]

    def snapshot(self):
        return self.dev.snapshot(quality=99)

    def ShellCmd(self, cmd, *args, **kwargs):
        """向链接的模拟器发送 shell 命令
        Args:
            cmd (str):命令字符串
        """
        return self.dev.shell(cmd)

    def get_frontend_app(self):
        """获取前台应用的包名"""
        return self.ShellCmd("dumpsys window | grep mCurrentFocus")

    def start_background_app(self, package_name):
        self.dev.start_app(package_name)
        self.ShellCmd("input keyevent 3")

    def start_app(self, package_name):
        self.dev.start_app(package_name)

    def stop_app(self, package_name):
        self.dev.stop_app(package_name)

    def is_game_running(self):
        apps = self.ShellCmd("ps")
        return "zhanjian2" in apps

    def text(self, t):
        self.logger.debug(f"Typing:{t}")
        self.dev.text(t)

    def click(self, x, y, times=1, delay=0.5, enable_subprocess=False, *args, **kwargs):
        """点击模拟器相对坐标 (x,y).
        Args:
            x,y:相对横坐标  (相对 960x540 屏幕)
            delay:点击后延时(单位为秒)
            enable_subprocess:是否启用多线程加速
            Note:
                if 'enable_subprocess' is True,arg 'times' must be 1
        Returns:
            enable_subprocess == False:None
            enable_subprocess == True:A class threading.Thread refers to this click subprocess
        """
        x, y = absolute_to_relative((x, y), (960, 540))
        self.relative_click(x, y, times, delay, enable_subprocess)

    def relative_click(self, x, y, times=1, delay=0.5, enable_subprocess=False):
        """点击模拟器相对坐标 (x,y).
        Args:
            x,y:相对坐标
            delay:点击后延时(单位为秒)
            enable_subprocess:是否启用多线程加速
            Note:
                if 'enable_subprocess' is True,arg 'times' must be 1
        Returns:
            enable_subprocess == False:None
            enable_subprocess == True:A class threading.Thread refers to this click subprocess
        """
        x, y = relative_to_absolute((x, y), self.resolution)

        if times < 1:
            raise ValueError("invalid arg 'times' " + str(times))
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        if enable_subprocess and times != 1:
            raise ValueError("subprocess enabled but arg 'times' is not 1 but " + str(times))
        if enable_subprocess:
            p = th.Thread(target=lambda: self.ShellCmd(f"input tap {str(x)} {str(y)}"))
            p.start()
            return p

        for _ in range(times):
            if self.config.SHOW_ANDROID_INPUT:
                self.logger.debug("click:", time.time(), x, y)
            self.ShellCmd(f"input tap {str(x)} {str(y)}")
            time.sleep(delay * self.config.DELAY)

    def swipe(self, x1, y1, x2, y2, duration=0.5, delay=0.5, *args, **kwargs):
        """匀速滑动模拟器相对坐标 (x1,y1) 到 (x2,y2).
        Args:
            x1,y1,x2,y2:相对坐标 (960x540 屏幕)
            duration:滑动总时间
            delay:滑动后延时(单位为秒)
        """
        x1, y1 = absolute_to_relative((x1, y1), (960, 540))
        x2, y2 = absolute_to_relative((x2, y2), (960, 540))
        self.relative_swipe(x1, y1, x2, y2, duration, delay, *args, **kwargs)

    def relative_swipe(self, x1, y1, x2, y2, duration=0.5, delay=0.5, *args, **kwargs):
        """匀速滑动模拟器相对坐标 (x1,y1) 到 (x2,y2).
        Args:
            x1,y1,x2,y2:相对坐标
            duration:滑动总时间
            delay:滑动后延时(单位为秒)
        """
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        x1, y1 = relative_to_absolute((x1, y1), self.resolution)
        x2, y2 = relative_to_absolute((x2, y2), self.resolution)
        duration = int(duration * 1000)
        input_str = f"input swipe {str(x1)} {str(y1)} {str(x2)} {str(y2)} {duration}"
        if self.config.SHOW_ANDROID_INPUT:
            self.logger.debug(input_str)
        self.ShellCmd(input_str)
        time.sleep(delay)

    def long_tap(self, x, y, duration=1, delay=0.5, *args, **kwargs):
        """长按相对坐标 (x,y)
        Args:
            x,y: 相对 (960x540 屏幕) 横坐标
            duration (int, optional): 长按时间(秒). Defaults to 1.
            delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
        """
        x, y = absolute_to_relative((x, y), (960, 540))
        self.relative_long_tap(x, y, duration, delay, *args, **kwargs)

    def relative_long_tap(self, x, y, duration=1, delay=0.5, *args, **kwargs):
        """长按相对坐标 (x,y)
        Args:
            x,y: 相对坐标
            duration (int, optional): 长按时间(秒). Defaults to 1.
            delay (float, optional): 操作后等待时间(秒). Defaults to 0.5.
        """
        if delay < 0:
            raise ValueError("arg 'delay' should be positive or 0")
        if duration <= 0.2:
            raise ValueError("duration time too short,arg 'duration' should greater than 0.2")
        x, y = relative_to_absolute((x, y), self.resolution)
        self.swipe(x, y, x, y, duration=duration, delay=delay, *args, **kwargs)
