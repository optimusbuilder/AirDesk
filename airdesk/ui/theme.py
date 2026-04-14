"""Theme primitives for the AirDesk visual layer."""

from dataclasses import dataclass
from typing import TypeAlias


ColorBGR: TypeAlias = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Theme:
    """Color tokens for overlays and virtual windows."""

    panel_fill: ColorBGR
    panel_border: ColorBGR
    panel_hover_border: ColorBGR
    panel_grabbed_border: ColorBGR
    panel_shadow: ColorBGR
    cursor: ColorBGR
    landmark: ColorBGR
    landmark_accent: ColorBGR
    text: ColorBGR


DEFAULT_THEME = Theme(
    panel_fill=(36, 26, 18),
    panel_border=(94, 170, 238),
    panel_hover_border=(120, 204, 255),
    panel_grabbed_border=(83, 255, 218),
    panel_shadow=(18, 14, 10),
    cursor=(80, 240, 255),
    landmark=(160, 220, 255),
    landmark_accent=(83, 255, 218),
    text=(245, 245, 245),
)
