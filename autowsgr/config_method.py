"""战斗方法配置模型。

这些模型描述地图节点、常规出征、战役和演习的执行参数，不属于用户
settings.yaml 的顶层持久化配置。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from autowsgr.application.controller.types import RepairMode


class NodeConfig(BaseModel):
    """单个地图节点的战斗配置。"""

    model_config = {'frozen': True}

    long_missile_support: bool = False
    detour: bool = False
    enemy_rules: list[str | list] = Field(default_factory=list)
    enemy_formation_rules: list[str | list] = Field(default_factory=list)
    SL_when_spot_enemy_fails: bool = False
    SL_when_detour_fails: bool = True
    SL_when_enter_fight: bool = False
    formation: int = 2
    formation_when_spot_enemy_fails: int | None = None
    night: bool = False
    proceed: bool = True
    proceed_stop: RepairMode | list[RepairMode] = RepairMode.severe_damage
    grade: str = ''


class FightConfig(BaseModel):
    """出征配置（通用）。"""

    model_config = {'frozen': True}

    chapter: int | str = 1
    map: int | str = 1
    fleet_id: int = 1
    fleet: list[str] | None = None
    repair_mode: RepairMode | list[RepairMode] = RepairMode.severe_damage
    selected_nodes: list[str] = Field(default_factory=list)
    fight_condition: int = 4

    @model_validator(mode='after')
    def _normalize_repair_mode(self) -> FightConfig:
        """将单个 repair_mode 展开为 6 个位置的列表。"""
        if not isinstance(self.repair_mode, list):
            modes = [self.repair_mode] * 6
            object.__setattr__(self, 'repair_mode', modes)
        return self


class BattleConfig(FightConfig):
    """战役配置。"""

    repair_mode: RepairMode | list[RepairMode] = RepairMode.moderate_damage


class ExerciseConfig(FightConfig):
    """演习配置。"""

    selected_nodes: list[str] = Field(default_factory=lambda: ['player', 'robot'])
    discard: bool = False
    exercise_times: int = 4
    robot: bool = True
    max_refresh_times: int = 2
