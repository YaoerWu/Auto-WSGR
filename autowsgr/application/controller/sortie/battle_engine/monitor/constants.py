"""模块功能：战斗阶段的视觉判据与战果识别校准。

上层调用：
- controller.sortie.battle_engine.monitor.checker：按阶段签名识别当前画面，
  按血条参考色、阵型区域与掉落页签名读取战果。

下层依赖：
- controller.sortie.battle_engine.constants：模板相对路径。
- controller.types：ShipDamageState 枚举。
- common.vision：像素规则、像素签名、ROI 与颜色类型。

边界：只描述"阶段长什么样、读哪里"；不含点击、不含流程推进与等待策略。
"""

from __future__ import annotations

from dataclasses import dataclass

from autowsgr.application.controller.sortie.battle_engine.constants import (
    PHASE_TEMPLATES,
    RESULT_GRADE_TEMPLATES,
)
from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase
from autowsgr.application.controller.types import ShipDamageState
from autowsgr.common.vision import ROI, Color, MatchStrategy, PixelRule, PixelSignature


@dataclass(frozen=True, slots=True)
class PhaseSignature:
    """一个战斗阶段的视觉判据。

    Attributes:
        template_keys: 候选模板键，任一命中即视为该阶段。
        exclude_template_keys: 否决键，任一命中则整体判为不匹配。
        pixel_signature: 没有专属模板时使用的像素签名。
        timeout_seconds: 等待该阶段出现的超时时间（秒）。
        confidence: 模板命中的最低分数。
        after_match_delay: 命中后的额外等待（秒），用于等 UI 动画结束。
    """

    template_keys: tuple[str, ...] = ()
    exclude_template_keys: tuple[str, ...] = ()
    pixel_signature: PixelSignature | None = None
    timeout_seconds: float = 15.0
    confidence: float = 0.8
    after_match_delay: float = 0.0

    @property
    def identifiable(self) -> bool:
        """是否有可执行的视觉判据。过渡态两项都为空，只能靠别的阶段推进。"""
        return bool(self.template_keys) or self.pixel_signature is not None


_GRADE_KEYS = tuple(f'grade_{grade.lower()}' for grade in RESULT_GRADE_TEMPLATES)
"""战果评级模板键（SS~D），顺序即优先级。"""

TEMPLATE_PATHS = {
    **PHASE_TEMPLATES,
    **{f'grade_{grade.lower()}': path for grade, path in RESULT_GRADE_TEMPLATES.items()},
}
"""阶段签名用到的全部模板键到相对路径的映射。"""

FORMATION_SIGNATURE = PixelSignature(
    name='choose_formation',
    strategy=MatchStrategy.ALL,
    rules=(
        PixelRule(0.9413, 0.2011, Color(227, 227, 227), tolerance=30.0),
        PixelRule(0.9375, 0.3644, Color(227, 227, 227), tolerance=30.0),
        PixelRule(0.9569, 0.5278, Color(227, 227, 227), tolerance=30.0),
        PixelRule(0.5050, 0.5678, Color(24, 101, 181), tolerance=30.0),
        PixelRule(0.5019, 0.9478, Color(26, 103, 183), tolerance=30.0),
        PixelRule(0.8531, 0.9367, Color(32, 134, 219), tolerance=30.0),
    ),
)
"""阵型选择界面：右上三个阵型按钮与底部三条操作栏。"""

PHASE_SIGNATURES: dict[CombatPhase, PhaseSignature] = {
    CombatPhase.PROCEED: PhaseSignature(
        template_keys=('proceed',),
        timeout_seconds=7.5,
        after_match_delay=0.5,
    ),
    # 过渡态：点下出征后的黑场与加载，没有专属画面，等下一个阶段自然覆盖。
    CombatPhase.START_FIGHT: PhaseSignature(timeout_seconds=3.0),
    # 旧框架的船坞已满模板没有对应图片资源，实际从未命中；船坞满在点下出征
    # 之后的编队检查里兜底，这里只是保留阶段位。
    CombatPhase.DOCK_FULL: PhaseSignature(timeout_seconds=3.0),
    CombatPhase.FIGHT_CONDITION: PhaseSignature(
        template_keys=('fight_condition',),
        timeout_seconds=22.5,
    ),
    CombatPhase.SPOT_ENEMY_SUCCESS: PhaseSignature(
        template_keys=('spot_enemy',),
        timeout_seconds=22.5,
    ),
    CombatPhase.FORMATION: PhaseSignature(
        pixel_signature=FORMATION_SIGNATURE,
        timeout_seconds=22.5,
    ),
    CombatPhase.MISSILE_ANIMATION: PhaseSignature(
        template_keys=('missile_animation',),
        timeout_seconds=3.0,
    ),
    CombatPhase.FIGHT_PERIOD: PhaseSignature(
        template_keys=('fight_period',),
        timeout_seconds=30.0,
    ),
    CombatPhase.NIGHT_PROMPT: PhaseSignature(
        template_keys=('night_battle',),
        timeout_seconds=150.0,
        after_match_delay=1.75,
    ),
    # 战果页判据用评级字母（SS~D）：只在战果页出现，经验页与准备页实测噪声
    # 不超过 0.48。旧判据 result_page 两页都有，还会被舰船立绘遮挡。
    CombatPhase.RESULT: PhaseSignature(
        template_keys=_GRADE_KEYS,
        timeout_seconds=90.0,
        confidence=0.85,
    ),
    # 经验结算页判据：MVP 徽章 + 无评级字母。MVP 徽章两页都出现，评级字母
    # 只出现在战果页，所以用否决键把战果页排除。
    CombatPhase.EXP_SETTLEMENT: PhaseSignature(
        template_keys=('result_page',),
        exclude_template_keys=_GRADE_KEYS,
        timeout_seconds=7.5,
        confidence=0.85,
    ),
    CombatPhase.GET_SHIP: PhaseSignature(
        template_keys=('get_ship', 'get_item'),
        timeout_seconds=5.0,
        after_match_delay=1.0,
    ),
    CombatPhase.FLAGSHIP_SEVERE_DAMAGE: PhaseSignature(
        template_keys=('flagship_damage',),
        timeout_seconds=7.5,
    ),
    CombatPhase.MAP_PAGE: PhaseSignature(
        template_keys=('end_map_page',),
        timeout_seconds=7.5,
    ),
    CombatPhase.EXERCISE_PAGE: PhaseSignature(
        template_keys=('end_exercise_page',),
        timeout_seconds=7.5,
    ),
    # 活动地图页的标题模板属于旧活动 UI 包，新框架没有对应资源，暂不可识别；
    # 第二阶段随活动 checker 补齐。
    CombatPhase.EVENT_MAP_PAGE: PhaseSignature(timeout_seconds=7.5),
}
"""各阶段的视觉判据与超时。"""

# ── 战果结算页校准 ─────────────────────────────────────────────────────────

RESULT_BLOOD_BAR_PROBE = {
    0: (60 / 960, 142 / 540),
    1: (60 / 960, 217 / 540),
    2: (60 / 960, 292 / 540),
    3: (60 / 960, 367 / 540),
    4: (60 / 960, 442 / 540),
    5: (60 / 960, 517 / 540),
}
"""结算页六个血条探测点（归一化）。"""

SHIP_SLOT_Y = [142 / 540, 217 / 540, 292 / 540, 367 / 540, 442 / 540, 517 / 540]
"""结算页六个槽位的纵向中心（归一化）。"""

BLOOD_REFERENCES: tuple[tuple[Color, ShipDamageState], ...] = (
    (Color(75, 168, 118), ShipDamageState.NORMAL),
    (Color(246, 184, 51), ShipDamageState.MODERATE),
    (Color(171, 18, 17), ShipDamageState.SEVERE),
    (Color(230, 58, 89), ShipDamageState.SEVERE),
    (Color(58, 60, 62), ShipDamageState.SEVERE),
    (Color(43, 87, 112), ShipDamageState.NO_SHIP),
)
"""血条颜色到血量状态的距离判定表。"""

# ── 索敌与掉落页校准 ───────────────────────────────────────────────────────

FORMATION_ROI = ROI(0.11, 0.05, 0.20, 0.15)
"""索敌成功界面敌方阵型文字区。"""

FORMATION_ALLOWLIST = '单纵复轮型梯形横阵'
"""敌方阵型 OCR 允许字符。"""

FORMATION_NAMES = {
    '单纵': '单纵阵',
    '复纵': '复纵阵',
    '轮型': '轮型阵',
    '梯形': '梯形阵',
    '单横': '单横阵',
}
"""OCR 片段到阵型名称的映射。"""

SHIP_DROP_PAGE_SIGNATURE = PixelSignature(
    name='ship_drop_page',
    strategy=MatchStrategy.ALL,
    rules=(
        PixelRule(0.0500, 0.9500, Color(20, 40, 68), tolerance=15.0),
        PixelRule(0.9500, 0.9500, Color(12, 35, 60), tolerance=15.0),
        PixelRule(0.9070, 0.1569, Color(16, 26, 46), tolerance=15.0),
        PixelRule(0.8906, 0.0972, Color(20, 26, 45), tolerance=15.0),
        PixelRule(0.8016, 0.2361, Color(33, 82, 125), tolerance=30.0),
        PixelRule(0.8300, 0.3000, Color(253, 236, 166), tolerance=15.0),
        PixelRule(0.8719, 0.2333, Color(23, 41, 67), tolerance=15.0),
        PixelRule(0.8109, 0.2681, Color(36, 58, 72), tolerance=30.0),
    ),
)
"""掉落页兜底像素签名。"""


__all__ = [
    'BLOOD_REFERENCES',
    'FORMATION_ALLOWLIST',
    'FORMATION_NAMES',
    'FORMATION_ROI',
    'FORMATION_SIGNATURE',
    'PHASE_SIGNATURES',
    'RESULT_BLOOD_BAR_PROBE',
    'SHIP_DROP_PAGE_SIGNATURE',
    'SHIP_SLOT_Y',
    'TEMPLATE_PATHS',
    'PhaseSignature',
]
