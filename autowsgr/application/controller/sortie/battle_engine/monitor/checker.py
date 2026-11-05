"""模块功能：战斗阶段的单帧识别与战果读取。

上层调用：
- application.combat.engine.recognizer：等待阶段时问一句当前画面是什么阶段。
- application.combat.engine.decision / settlement / handlers：读敌方阵型、战果、
  掉落页与任意模板是否出现。

下层依赖：
- controller.sortie.battle_engine.monitor.constants：阶段签名、战果校准与模板路径。
- controller.types：ShipDamageState 枚举。
- common.vision：截图、模板匹配、像素匹配与 OCR。

边界：只读画面并返回识别结论；不点击、不推进流程、不写战斗历史、不做超时等待。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_engine.monitor.constants import (
    BLOOD_REFERENCES,
    FORMATION_ALLOWLIST,
    FORMATION_NAMES,
    FORMATION_ROI,
    PHASE_SIGNATURES,
    RESULT_BLOOD_BAR_PROBE,
    SHIP_DROP_PAGE_SIGNATURE,
    SHIP_SLOT_Y,
    TEMPLATE_PATHS,
    PhaseSignature,
)
from autowsgr.application.controller.types import ShipDamageState
from autowsgr.common.system.logger import get_logger
from autowsgr.common.vision import (
    Color,
    RecognitionProfile,
    adapters,
    expect_ocr,
    expect_template,
    screenshot,
)
from autowsgr.common.vision.adapters.template_matching import load_template


if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy

    from autowsgr.application.controller.sortie.battle_engine.monitor.types import CombatPhase
    from autowsgr.common.vision import Template
    from autowsgr.dispatch.context import ContextHandle

_log = get_logger('combat')


@dataclass(frozen=True, slots=True)
class ShipDropResult:
    """掉落页 OCR 的原始结果。

    Attributes:
        ship_name: 识别到的舰名，未识别为空。
        ship_type: 识别到的舰种，未识别为空。
    """

    ship_name: str | None
    ship_type: str | None


# ══════════════════════════════════════════════════════════════════════════════
# 阶段识别
# ══════════════════════════════════════════════════════════════════════════════


def read_combat_phase(
    ctx: ContextHandle,
    candidates: Sequence[CombatPhase],
) -> CombatPhase | None:
    """截图一次，判断当前画面属于候选阶段中的哪一个。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        candidates: 候选阶段，按优先级排列。

    Returns:
        命中的阶段；一个都没命中时为空。
    """
    return read_phase_from_frame(screenshot(ctx), candidates)


def read_phase_from_frame(
    frame: numpy.ndarray,
    candidates: Sequence[CombatPhase],
) -> CombatPhase | None:
    """在给定帧上判断当前阶段，不截图、不等待。

    已经拿到帧的轮询路径用它，避免为了每次判定重复截图。

    Args:
        frame: 当前截图帧。
        candidates: 候选阶段，按优先级排列。

    Returns:
        命中的阶段；一个都没命中时为空。
    """
    signatures = [(phase, _signature_of(phase)) for phase in candidates]
    keys = tuple(
        dict.fromkeys(
            key
            for _, signature in signatures
            for key in (*signature.template_keys, *signature.exclude_template_keys)
        ),
    )

    # 一次匹配算全部候选的分数：不同阶段的置信度不同，所以用最低的那档
    # 当作匹配下限，再逐阶段拿分数和各自的阈值比。
    scores: dict[str, float] = {}
    if keys:
        floor = min(signature.confidence for _, signature in signatures)
        results = adapters.match_templates(
            frame,
            [_load_template(key) for key in keys],
            confidence=floor,
        )
        scores = {key: result.score for key, result in zip(keys, results, strict=True)}

    for phase, signature in signatures:
        if not signature.identifiable:
            continue
        if signature.template_keys:
            if not _any_above(scores, signature.template_keys, signature.confidence):
                continue
            if _any_above(scores, signature.exclude_template_keys, signature.confidence):
                continue
            return phase
        if (
            signature.pixel_signature is not None
            and adapters.match_pixels(frame, signature.pixel_signature)[0].matched
        ):
            return phase
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 战果读取
# ══════════════════════════════════════════════════════════════════════════════


def check_template_exist(
    ctx: ContextHandle,
    template: Template,
    *,
    confidence: float = 0.8,
) -> bool:
    """判断当前画面是否出现指定模板。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        template: 待检查的模板。
        confidence: 命中阈值。

    Returns:
        命中返回真。
    """
    return expect_template(
        ctx,
        template=template,
        confidence=confidence,
        attempts=1,
    ).satisfied


def check_ship_drop_page(ctx: ContextHandle) -> bool:
    """用像素签名判断当前是否停在掉落页。

    掉落页的模板匹配在页面动画期间可能失效，主循环用它兜底判断，避免连续点击
    把掉落直接点过去。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。

    Returns:
        当前画面符合掉落页特征返回真。
    """
    return is_ship_drop_page(screenshot(ctx))


def is_ship_drop_page(frame: numpy.ndarray) -> bool:
    """用像素签名判断给定帧是不是掉落页。

    Args:
        frame: 当前截图帧。

    Returns:
        符合掉落页特征返回真。
    """
    return _match_signature(frame, SHIP_DROP_PAGE_SIGNATURE)


def read_result_grade(ctx: ContextHandle, *, attempts: int = 5) -> str:
    """读取战果等级。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        attempts: 最大识别次数。

    Returns:
        等级字母；识别窗口耗尽仍没命中时返回空串，由调用方决定如何处理。
    """
    templates = tuple(_load_template(path) for path in _grade_paths())
    result = expect_template(
        ctx,
        template=templates,
        confidence=0.85,
        attempts=attempts,
        interval_seconds=0.25,
    )
    for grade, match in zip(_grade_names(), result.observation, strict=True):
        if match.matched:
            return grade
    return ''


def read_ship_stats(
    ctx: ContextHandle,
    pre_battle_stats: list[ShipDamageState],
) -> list[ShipDamageState]:
    """读取结算页六个槽位的血量状态。

    出战前就没有舰船的槽位直接沿用无船状态，不参与颜色判定。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        pre_battle_stats: 出战前的血量状态，用于判断空槽。

    Returns:
        按槽位顺序排列的血量状态。
    """
    frame = screenshot(ctx)
    height, width = frame.shape[:2]
    stats: list[ShipDamageState] = []
    for slot, (x_ratio, y_ratio) in RESULT_BLOOD_BAR_PROBE.items():
        if pre_battle_stats[slot] is ShipDamageState.NO_SHIP:
            stats.append(ShipDamageState.NO_SHIP)
            continue
        x = min(round(x_ratio * width), width - 1)
        y = min(round(y_ratio * height), height - 1)
        red, green, blue = frame[y, x][:3]
        stats.append(_classify_blood(Color(int(red), int(green), int(blue))))
    _log.info('[COMBAT] 结算页血量：{}', [state.name for state in stats])
    return stats


def read_mvp(ctx: ContextHandle) -> int | None:
    """读取 MVP 槽位。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。

    Returns:
        从 1 开始的槽位号；没有 MVP 徽章时为空。
    """
    result = expect_template(
        ctx,
        template=_load_template(TEMPLATE_PATHS['mvp_badge']),
        confidence=0.8,
        attempts=1,
    )
    center = result.observation[0].center
    if not result.satisfied or center is None:
        return None
    slot = min(range(len(SHIP_SLOT_Y)), key=lambda index: abs(center[1] - SHIP_SLOT_Y[index]))
    _log.info('[COMBAT] MVP 位置：{}', slot + 1)
    return slot + 1


def read_enemy_formation(ctx: ContextHandle) -> str:
    """读取索敌成功界面的敌方阵型。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。

    Returns:
        阵型名称；没有识别到文字时返回空串。
    """
    result = expect_ocr(
        ctx,
        roi=FORMATION_ROI,
        allowlist=FORMATION_ALLOWLIST,
        recognition_profile=RecognitionProfile.SINGLE_LINE,
        attempts=1,
    )
    text = ''.join(detection.recognized_text for detection in result.observation).strip()
    if not text:
        _log.debug('[COMBAT] 阵型 OCR 无结果')
        return ''
    for key, name in FORMATION_NAMES.items():
        if key in text:
            return name
    return text


def read_enemy_composition(
    ctx: ContextHandle,  # noqa: ARG001 - P0 降级占位，第二阶段随 checker 重做
    *,
    mode: str = 'fight',
) -> dict[str, int]:
    """读取敌方编成的舰种数量。

    舰种图标识别依赖原生识别库，P0 只保留调用入口，返回空编成让上层规则退化为
    不按敌人规则决策。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        mode: 索敌场景，fight 为常规战，exercise 为演习。

    Returns:
        舰种到数量的映射，P0 恒为空。
    """
    _log.warning('[COMBAT] 敌方编成识别未接入（mode={}），按空编成决策', mode)
    return {}


def read_ship_drop(
    ctx: ContextHandle,  # noqa: ARG001 - P0 降级占位，第二阶段随 checker 重做
    *,
    attempts: int = 5,  # noqa: ARG001 - P0 降级占位，第二阶段随 checker 重做
) -> ShipDropResult:
    """读取掉落页的舰名与舰种。

    掉落页文字带旋转，P0 只保留调用入口，返回空结果让上层跳过掉落统计。

    Args:
        ctx: 提供设备服务的统一 ContextHandle。
        attempts: 最大识别次数。

    Returns:
        掉落结果，P0 恒为空结果。
    """
    _log.warning('[COMBAT] 掉落识别未接入，跳过本次掉落统计')
    return ShipDropResult(ship_name=None, ship_type=None)


# ══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ══════════════════════════════════════════════════════════════════════════════


@cache
def _load_template(key: str) -> Template:
    """按模板键加载模板；同一路径只读盘一次。"""
    return load_template(TEMPLATE_PATHS[key])


def _grade_names() -> tuple[str, ...]:
    """战果等级模板键里的字母，顺序即判定优先级。"""
    return tuple(key.removeprefix('grade_').upper() for key in _grade_keys())


def _grade_keys() -> tuple[str, ...]:
    """战果等级模板键（grade_ss ~ grade_d）。"""
    return tuple(key for key in TEMPLATE_PATHS if key.startswith('grade_'))


def _grade_paths() -> tuple[str, ...]:
    """战果等级模板的相对路径，顺序与 _grade_names 一致。"""
    return tuple(TEMPLATE_PATHS[key] for key in _grade_keys())


def _signature_of(phase: CombatPhase) -> PhaseSignature:
    """取阶段的视觉判据；未登记的阶段按纯等待处理。"""
    return PHASE_SIGNATURES.get(phase, PhaseSignature())


def _any_above(scores: dict[str, float], keys: Sequence[str], confidence: float) -> bool:
    """判断给定模板键里是否有任一命中。"""
    return any(scores.get(key, 0.0) >= confidence for key in keys)


def _classify_blood(pixel: Color) -> ShipDamageState:
    """按最近参考色把血条像素归类为血量状态。"""
    best_state = ShipDamageState.NORMAL
    best_distance = float('inf')
    for reference, state in BLOOD_REFERENCES:
        distance = pixel.distance(reference)
        if distance < best_distance:
            best_distance = distance
            best_state = state
    return best_state


def _match_signature(frame: numpy.ndarray, signature: object) -> bool:
    """在给定帧上判定像素签名是否全部命中。"""
    return adapters.match_pixels(frame, signature)[0].matched


__all__ = [
    'ShipDropResult',
    'check_ship_drop_page',
    'check_template_exist',
    'is_ship_drop_page',
    'read_combat_phase',
    'read_enemy_composition',
    'read_enemy_formation',
    'read_mvp',
    'read_phase_from_frame',
    'read_result_grade',
    'read_ship_drop',
    'read_ship_stats',
]
