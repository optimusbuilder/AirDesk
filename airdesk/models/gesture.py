"""Gesture interpretation state models."""

from dataclasses import dataclass

from airdesk.models.hand import PixelPoint


@dataclass(slots=True)
class GestureState:
    """Derived gesture signals produced from hand landmark geometry."""

    cursor_px: PixelPoint | None = None
    raw_cursor_px: PixelPoint | None = None
    pinch_ratio: float = 0.0
    pinch_active: bool = False
    pinch_started: bool = False
    pinch_ended: bool = False
    pinch_finger: str | None = None  # "index" or "middle"
    clutch_pose: bool = False
    tracking_stable: bool = False
