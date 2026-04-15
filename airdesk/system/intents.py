"""High-level system-control intents derived from gestures."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from airdesk.models.hand import PixelPoint


NormalizedPoint: TypeAlias = tuple[float, float]


class PointerPhase(StrEnum):
    """Pointer phases shared across system-control backends."""

    IDLE = "idle"
    MOVE = "move"
    PRESS = "press"
    DRAG = "drag"
    RELEASE = "release"
    LOST = "lost"


@dataclass(slots=True)
class SystemControlState:
    """One frame of backend-agnostic system-control intent."""

    enabled: bool = False
    backend_name: str = "disabled"
    phase: PointerPhase = PointerPhase.IDLE
    frame_cursor_px: PixelPoint | None = None
    normalized_cursor: NormalizedPoint | None = None
    button_down: bool = False
    effect_label: str = "System control disabled"
