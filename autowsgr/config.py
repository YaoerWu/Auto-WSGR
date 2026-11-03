"""配置管理 — 基于 Pydantic v2。

配置从 YAML 文件加载，经过 Pydantic 校验后生成不可变的配置对象。
所有配置模型都继承 ModuleConfig：不可变，且拒绝未声明的字段。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from autowsgr.application.fleet_select.config import FleetSelectConfig
from autowsgr.application.runtime.types import GameAPP, LoginServer
from autowsgr.common.device.config import DeviceConfig
from autowsgr.common.system.config import LogConfig, ModuleConfig
from autowsgr.common.system.files import load_yaml
from autowsgr.common.system.logger import get_logger


_log = get_logger('infra')


class AccountConfig(BaseModel):
    """游戏账号配置。"""

    model_config = {'frozen': True}

    game_app: GameAPP = GameAPP.official
    """游戏渠道(决定 Android 包名)"""

    game_server: LoginServer = LoginServer.default
    """登录区服；默认表示不处理换区。"""

    @property
    def package_name(self) -> str:
        """Android 包名。"""
        return self.game_app.package_name


class OCRConfig(BaseModel):
    """OCR 引擎配置。"""

    model_config = {'frozen': True}

    # 舰名匹配
    ship_name_match_confidence: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    """舰名匹配置信度：0 为关闭，0.65 为默认，1 为完全匹配；越大越严格，建议勿改。"""
    ship_name_corrections: dict[str, str] = Field(default_factory=dict)
    """用户舰名 OCR 修正规则，格式为 ``OCR 原文: SHIPNAMES 标准舰名``。"""
    ship_name_aliases: dict[str, str] = Field(default_factory=dict)
    """用户舰名别名，格式为 ``用户自定义名: SHIPNAMES 标准舰名``。"""

    @field_validator('ship_name_corrections', 'ship_name_aliases', mode='before')
    @classmethod
    def _normalize_ship_name_corrections(cls, value: object) -> dict[str, str]:
        """逐条清理用户舰名配置；格式错误的条目直接跳过。"""
        if value is None:
            return {}
        if not isinstance(value, dict):
            _log.warning('OCR 用户舰名配置必须是映射，已跳过全部配置')
            return {}

        corrections: dict[str, str] = {}
        for raw_text, ship_name in value.items():
            if not isinstance(raw_text, str) or not isinstance(ship_name, str):
                _log.warning('跳过格式错误的 OCR 用户舰名配置: {} -> {}', raw_text, ship_name)
                continue
            source = raw_text.strip()
            target = ship_name.strip()
            if not source or not target:
                _log.warning('跳过内容为空的 OCR 用户舰名配置')
                continue
            corrections[source] = target
        return corrections


# ── 自动化任务配置 ──
class NormalFightTaskConfig(BaseModel):
    """单个常规战任务配置。

    兼容 classic 的 ``[plan_name, fleet_id, target_times]`` 列表写法
    (经 :func:`_parse_normal_fight_tasks` 解析), 也支持纯字符串 (仅 plan 名)
    或完整字典。
    """

    model_config = {'frozen': True}

    name: str
    """常规战计划名 (如 ``8-5AI-only1DD``), 解析为 ``autowsgr/common/data/plan/normal_fight/`` 下的文件。"""
    fleet_id: int | None = None
    """出征舰队编号; 留空则用 plan 内配置。"""
    times: int | None = None
    """目标出击次数; ``None`` 表示无限 (空闲填充, 仅受全局上限约束)。

    .. note:: ``times=None`` (无限) 且未开启 ``stop_max_ship`` /
       ``stop_max_loot`` / ``quick_repair_limit`` 任一上限时, 常规战会持续
       产出任务、永远抢占浴室修理 (优先级更低), 致浴室修理永不执行。
    """


class DailyAutomationConfig(BaseModel):
    """日常自动化设置。"""

    model_config = {'frozen': True}

    # 基础日常
    auto_expedition: bool = True
    """自动重复远征"""
    auto_gain_bonus: bool = True
    """任务完成时自动点击"""
    auto_bath_repair: bool = True
    """空闲时自动澡堂修理"""
    auto_set_support: bool = False
    """自动开启战役支援"""
    bath_repair_blacklist: list[str] = Field(default_factory=list)
    """浴室修理黑名单:这些舰船名(中文全名)不会被自动浴室修理。"""

    # 战役
    auto_battle: bool = True
    """自动打完每日战役次数"""
    battle_type: Literal[
        '简单航母',
        '简单潜艇',
        '简单驱逐',
        '简单巡洋',
        '简单战列',
        '困难航母',
        '困难潜艇',
        '困难驱逐',
        '困难巡洋',
        '困难战列',
    ] = '困难潜艇'
    """打哪个战役"""

    # 演习
    auto_exercise: bool = True
    """自动打完每日三次演习"""
    exercise_fleet_id: int | None = None
    """演习出征舰队"""

    # 常规战
    auto_normal_fight: bool = True
    """按自定义任务进行常规战"""
    normal_fight_tasks: list[NormalFightTaskConfig] = Field(default_factory=list)
    """常规战任务列表; 兼容 classic ``[name, fleet, times]`` 写法 (见下方校验器)。"""
    quick_repair_limit: int | None = None
    """快修消耗上限"""
    stop_max_ship: bool = False
    """获取当天上限 500 船后终止"""
    stop_max_loot: bool = False
    """获取当天上限 50 胖次后终止"""

    @field_validator('normal_fight_tasks', mode='before')
    @classmethod
    def _parse_normal_fight_tasks(cls, v: object) -> list[dict[str, Any]]:
        """把 classic ``[name, fleet, times]`` 列表 / 纯字符串 / dict 统一成 dict。

        classic 的 user_settings.yaml 里写法是::

            normal_fight_tasks:
              - [8-5AI-only1DD, 4, 900]   # [plan, fleet_id, target_times]

        Pydantic 默认无法把嵌套 list 塞进结构化模型, 这里在校验前转换。
        """
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError(f'normal_fight_tasks 应为列表, 得到 {type(v).__name__}')
        result: list[dict[str, Any]] = []
        for item in v:
            if isinstance(item, str):
                result.append({'name': item})
            elif isinstance(item, dict):
                result.append(item)
            elif isinstance(item, (list, tuple)):
                # [name, fleet_id, target_times]
                if len(item) < 1:
                    raise ValueError(f'常规战任务条目不能为空: {item!r}')
                entry: dict[str, Any] = {'name': str(item[0])}
                if len(item) >= 2 and item[1] is not None:
                    entry['fleet_id'] = int(item[1])  # type: ignore[arg-type]
                if len(item) >= 3 and item[2] is not None:
                    entry['times'] = int(item[2])  # type: ignore[arg-type]
                result.append(entry)
            else:
                raise TypeError(f'无法识别的常规战任务条目: {item!r}')
        return result


class DecisiveConfig(BaseModel):
    """决战自动化配置。"""

    model_config = {'frozen': True}

    chapter: int = 6
    """决战章节 (1-6)"""
    decisive_rounds: int = 1
    """决战连续执行轮数"""
    level1: list[str] = Field(
        default_factory=lambda: ['鲃鱼', 'U-1206', 'U-47', '射水鱼', 'U-96', 'U-1405']
    )
    """一级舰队"""
    level2: list[str] = Field(default_factory=lambda: ['U-81', '大青花鱼'])
    """二级舰队"""
    flagship_priority: list[str] = Field(
        default_factory=lambda: ['U-1405', 'U-47', 'U-96', 'U-1206']
    )
    """旗舰优先级队列"""
    repair_level: int = 1
    """维修策略 (1=中破修, 2=大破修)"""
    use_quick_repair: bool = True
    """是否使用快修"""
    full_destroy: bool = False
    """船舱满了是否解装舰船"""
    useful_skill: bool = False
    """充分利用技能, 开启时要求地图1必须为Lv1+Lv2中的船; 其余地图至少一半的船为Lv1中的船"""
    useful_skill_strict: bool = False
    """严格利用技能, 开启时要求地图1技能不能获取+1的船; useful_skill为True时本设置才生效"""

    @field_validator('chapter')
    @classmethod
    def _validate_chapter(cls, v: int) -> int:
        if not 1 <= v <= 6:
            raise ValueError('决战章节必须为 1-6 之间的整数')
        return v


# ── 顶层用户配置 ──


class UserConfig(ModuleConfig):
    """用户配置（顶层聚合）。"""

    LOG: LogConfig = Field(default_factory=LogConfig)  # 日志配置。
    DEVICE: DeviceConfig = Field(default_factory=DeviceConfig)  # 设备配置。
    FLEET_SELECT: FleetSelectConfig = Field(default_factory=FleetSelectConfig)  # 换船配置。

    @classmethod
    def from_yaml(cls, path: str | Path) -> UserConfig:
        """从 YAML 文件加载配置。

        raw dict 先经 :func:`detect_legacy_user_config` 检测 classic 老版本字段;
        命中则抛 :class:`LegacyConfigError` 提示用户运行迁移工具
        (tools/migrate_config.py), **不再自动迁移 / 回写**。干净则交 Pydantic 校验。

        Parameters
        ----------
        path:
            用户配置文件路径 (YAML)。

        Returns
        -------
        UserConfig
            校验后的不可变配置对象。
        """
        from autowsgr.config_compat import (
            LegacyConfigError,
            detect_legacy_user_config,
        )

        data = load_yaml(path, allowed_root=Path(path).expanduser().resolve().parent)
        legacy = detect_legacy_user_config(data)
        if legacy:
            raise LegacyConfigError(
                f'配置文件 {path} 含 classic 老版本字段, 拒绝加载:\n  - '
                + '\n  - '.join(legacy)
                + '\n请先运行迁移工具生成新配置 (原文件不动):\n'
                f'  python tools/migrate_config.py --usersettings "{path}"\n'
                '(可加 --planroot <计划目录> 一起迁移; 默认输出到 migrated_config/)',
            )
        return cls.model_validate(data)


# 默认配置文件名（当前目录下）
_DEFAULT_CONFIG_FILENAME = 'usersettings.yaml'


class ConfigManager:
    """配置管理器 — 提供加载入口。"""

    @staticmethod
    def load(path: str | Path | None = None) -> UserConfig:
        """从文件加载用户配置。

        查找策略:

        1. 如果显式指定了 *path*，直接加载该文件；文件不存在时回退默认值。
        2. 如果 *path* 为 ``None``，尝试当前工作目录下的
           ``usersettings.yaml``；文件存在则加载，不存在则使用默认值。

        Parameters
        ----------
        path:
            用户配置文件路径 (YAML)。为 ``None`` 时自动检测。

        Returns
        -------
        UserConfig
            校验后的不可变配置对象。
        """
        if path is not None:
            path = Path(path)
            if not path.exists():
                _log.warning('配置文件 {} 不存在，使用默认配置', path)
                return UserConfig()
            config = UserConfig.from_yaml(path)
            _log.info('已加载配置: {}', path)
            return config

        # 未指定路径 → 尝试当前目录下的默认配置
        default = Path.cwd() / _DEFAULT_CONFIG_FILENAME
        if default.exists():
            _log.info('检测到默认配置文件: {}', default)
            config = UserConfig.from_yaml(default)
            _log.info('已加载配置: {}', default)
            return config

        _log.info('未指定配置文件且未检测到 {}，使用内置默认配置', _DEFAULT_CONFIG_FILENAME)
        return UserConfig()
