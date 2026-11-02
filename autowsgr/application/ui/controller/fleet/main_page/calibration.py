"""出征准备页面的坐标、颜色和 OCR 校准值。"""

from __future__ import annotations

from autowsgr.application.vision.calibration._loader import color, point, points, signature
from autowsgr.application.vision.calibration._loader import param as color_param
from autowsgr.application.vision.calibration._loader import param as ocr_param


FLEET_ACTIVE = color('battle_prep', 'fleet_active')
PANEL_ACTIVE = color('battle_prep', 'panel_active')
AUTO_SUPPLY_ON = color('battle_prep', 'auto_supply_on')
STATE_TOLERANCE = color_param('battle_prep', 'state_tolerance')

FLEET_PROBE = dict(enumerate(points('battle_prep', 'fleet_probe'), 1))
SUPPORT_PROBE = point('battle_prep', 'support_probe')
AUTO_SUPPLY_PROBE = point('battle_prep', 'auto_supply_probe')

CLICK_BACK = point('battle_prep', 'back')
CLICK_FLEET = dict(enumerate(points('battle_prep', 'fleet'), 1))
CLICK_SUPPORT = point('battle_prep', 'support')
CLICK_AUTO_SUPPLY = point('battle_prep', 'auto_supply')
CLICK_START_BATTLE = point('battle_prep', 'start_battle')
CLICK_SHIP_SLOT = dict(enumerate(points('battle_prep', 'ship_slot')))
BLOOD_BAR_PROBE = dict(enumerate(points('battle_prep', 'blood_bar')))
PANEL_PROBES = {
    name: point('battle_prep', f'panel_probe.{name}')
    for name in ('stats', 'quick_supply', 'quick_repair', 'equipment')
}
PANEL_CLICKS = {
    name: point('battle_prep', f'click_panel.{name}')
    for name in ('stats', 'quick_supply', 'quick_repair', 'equipment')
}
PAGE_SIGNATURE = signature('battle_prep', 'page')

SUPPORT_ENABLE = color('battle_prep', 'support_enable')
SUPPORT_DISABLE = color('battle_prep', 'support_disable')
SUPPORT_EXHAUSTED = color('battle_prep', 'support_exhausted')

SHIP_LEVEL_CROP = {
    i: tuple(crop) for i, crop in enumerate(ocr_param('battle_prep', 'ship_level_crop'))
}
SHIP_TYPE_CROP = {
    i: tuple(crop) for i, crop in enumerate(ocr_param('battle_prep', 'ship_type_crop'))
}


__all__ = [
    'AUTO_SUPPLY_ON',
    'AUTO_SUPPLY_PROBE',
    'BLOOD_BAR_PROBE',
    'CLICK_AUTO_SUPPLY',
    'CLICK_BACK',
    'CLICK_FLEET',
    'CLICK_SHIP_SLOT',
    'CLICK_START_BATTLE',
    'CLICK_SUPPORT',
    'FLEET_ACTIVE',
    'FLEET_PROBE',
    'PANEL_ACTIVE',
    'PANEL_CLICKS',
    'PANEL_PROBES',
    'PAGE_SIGNATURE',
    'SHIP_LEVEL_CROP',
    'SHIP_TYPE_CROP',
    'STATE_TOLERANCE',
    'SUPPORT_DISABLE',
    'SUPPORT_ENABLE',
    'SUPPORT_EXHAUSTED',
    'SUPPORT_PROBE',
]
