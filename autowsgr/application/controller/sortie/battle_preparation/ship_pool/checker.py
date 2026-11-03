"""模块功能：识别船池页面属于哪一类，并读出列表上的文字。

上层调用：
- application.navigation.registry：判断当前画面是不是船池页面，供导航到达确认使用。
- application.fleet_select.operation.ship_select：读船池类别决定搜索框能不能用，并读列表文字决定点哪张卡。

下层依赖：
- application.controller.sortie.battle_preparation.ship_pool.constants：识别区域与模板名。
- application.controller.template：加载本模块模板。
- common.vision：模板与 OCR 识别入口。

边界：只读页面事实，不比对舰名清单、不判断这张卡是不是目标船、不点击。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from autowsgr.application.controller.sortie.battle_preparation.ship_pool import constants
from autowsgr.application.controller.template import load_ui_template
from autowsgr.common.system.enums import StrEnum
from autowsgr.common.vision import (
    RecognitionProfile,
    RecognitionResult,
    expect_ocr,
    expect_pixels,
    expect_template,
)


if TYPE_CHECKING:
    from autowsgr.common.vision import ROI, Template, TemplateMatchResult
    from autowsgr.dispatch.context import ContextHandle


# 进入或离开船池页面的等待窗口：页面切换有转场动画，给足 5 秒。
_NAV_CONFIRM_ATTEMPTS = 5
_NAV_CONFIRM_INTERVAL_SECONDS = 1.0


# ── 识别数据 ────────────────────────────────────────────────────────────────

# 四个特征模板与各自的死区域，顺序即识别结果顺序。定类规则：
# 强化满隐藏 → 强化；快速选择 → 拆解；快速编队无星标 → 决战；有星标 → 出征。
_KIND_FEATURES: tuple[tuple[str, ROI], ...] = (
    (constants.QUICK_STRENGTHEN_TEMPLATE, constants.QUICK_STRENGTHEN_ROI),
    (constants.QUICK_SELECT_TEMPLATE, constants.QUICK_SELECT_ROI),
    (constants.QUICK_FORMATION_TEMPLATE, constants.QUICK_FORMATION_ROI),
    (constants.STAR_TEMPLATE, constants.STAR_ROI),
)


# ── 识别模型 ────────────────────────────────────────────────────────────────


class ShipPoolKind(StrEnum):
    """船池页面按入口分出的类别。"""

    ACADEMY = '学院船池'
    STRENGTHEN = '强化船池'
    DISMANTLE = '拆解船池'
    SORTIE = '出征船池'
    DECISIVE = '决战船池'


@dataclass(frozen=True, slots=True)
class ShipListText:
    """船池列表上的一段文字及其归一化位置。"""

    text: str
    center: tuple[float, float]
    region: tuple[float, float, float, float]


# ── 识别入口 ────────────────────────────────────────────────────────────────


def check_ship_pool_page(
    ctx: ContextHandle,
    *,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
    absent: bool = False,
) -> bool:
    """判断当前画面是不是船池页面。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。
        absent: 期望船池页面已经离开时为真。

    Returns:
        页面特征成立（或按 absent 期望消失）时为 True。
    """
    return _read_features(
        ctx, attempts=attempts, interval_seconds=interval_seconds, absent=absent
    ).satisfied


def read_ship_pool_kind(
    ctx: ContextHandle,
    *,
    attempts: int = 1,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> ShipPoolKind | None:
    """读一次画面，判断当前船池页面属于哪一类。

    四个特征模板一次性在同一帧里匹配：它们各自的搜索区域只有 1px 余量，既省掉四帧
    截图，也避免了全图搜索时「快速编队」在出征、演习、决战三页互为满分的问题。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数；读取语义下默认只截一帧。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        船池类别；四个特征都没命中时返回 None，说明当前页面不是船池。
    """
    matches = _read_features(
        ctx, attempts=attempts, interval_seconds=interval_seconds, absent=False
    ).observation
    return _kind_from_matches(matches)


def check_search_input(
    ctx: ContextHandle,
    *,
    attempts: int = _NAV_CONFIRM_ATTEMPTS,
    interval_seconds: float = _NAV_CONFIRM_INTERVAL_SECONDS,
) -> bool:
    """判断船池页面的搜索输入框是否已经唤起软键盘。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。
        attempts: 最大识别次数。
        interval_seconds: 两次识别之间的等待秒数。

    Returns:
        输入态签名成立时为 True。
    """
    return expect_pixels(
        ctx,
        signature=constants.SEARCH_INPUT_SIGNATURE,
        attempts=attempts,
        interval_seconds=interval_seconds,
    ).satisfied


def read_ship_list_texts(ctx: ContextHandle) -> tuple[ShipListText, ...]:
    """读取船池列表区域上的全部文字及其归一化中心。

    一次识别只截一帧。识别整帧再按列表区域的中心点筛选：裁切后单独识别会丢掉卡片
    右缘的小字等级行（实测同名两卡只读出 Lv.110、Lv.8 丢失且只剩星级），整帧识别稳定。
    文字原样返回，是否属于舰名清单由上层比对；没有检测框的结果无法换算位置，直接丢弃。

    Args:
        ctx: 提供设备服务和截图事实的 dispatch 上下文句柄。

    Returns:
        按画面阅读顺序排列的文字与中心列表。
    """
    result = expect_ocr(ctx, recognition_profile=RecognitionProfile.FULL, attempts=1)
    frame = result.screenshot
    if frame is None:
        return ()

    height, width = frame.shape[:2]
    left, top, right, bottom = constants.SHIP_LIST_ROI.to_absolute(width, height)
    texts: list[ShipListText] = []
    for detection in result.observation:
        text = detection.recognized_text.strip()
        region = detection.text_region
        if not text or region is None:
            continue
        # 整帧识别的坐标已经是画面坐标，只保留中心落在列表区域内的文字。
        region_x1, region_y1, region_x2, region_y2 = region
        center_x = (region_x1 + region_x2) / 2
        center_y = (region_y1 + region_y2) / 2
        if not (left <= center_x <= right and top <= center_y <= bottom):
            continue
        texts.append(
            ShipListText(
                text=text,
                center=(center_x / width, center_y / height),
                region=(
                    region_x1 / width,
                    region_y1 / height,
                    region_x2 / width,
                    region_y2 / height,
                ),
            )
        )
    return tuple(texts)


# ── 私有辅助 ────────────────────────────────────────────────────────────────


def _read_features(
    ctx: ContextHandle,
    *,
    attempts: int,
    interval_seconds: float,
    absent: bool,
) -> RecognitionResult[list[TemplateMatchResult]]:
    """在同一帧里匹配四个特征模板，判定交给 expect_template 的重试循环。"""
    features = _load_features()
    return expect_template(
        ctx,
        template=tuple(template for template, _roi in features),
        roi=tuple(roi for _template, roi in features),
        attempts=attempts,
        interval_seconds=interval_seconds,
        absent=absent,
    )


def _kind_from_matches(matches: list[TemplateMatchResult]) -> ShipPoolKind | None:
    """按特征命中组合定出船池类别。"""
    strengthen, select, formation, star = (match.matched for match in matches)
    if strengthen:
        return ShipPoolKind.STRENGTHEN
    if select:
        return ShipPoolKind.DISMANTLE
    if formation:
        return ShipPoolKind.DECISIVE if not star else ShipPoolKind.SORTIE
    if star:
        return ShipPoolKind.ACADEMY
    return None


def _load_features() -> tuple[tuple[Template, ROI], ...]:
    """按固定顺序加载四个特征模板；模板按参数缓存，重复调用不读盘。"""
    return tuple(
        (load_ui_template(constants.TEMPLATE_NAMESPACE, filename), roi)
        for filename, roi in _KIND_FEATURES
    )


__all__ = [
    'ShipListText',
    'ShipPoolKind',
    'check_search_input',
    'check_ship_pool_page',
    'read_ship_list_texts',
    'read_ship_pool_kind',
]
