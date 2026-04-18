"""High-level system-control intents derived from gestures."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from airdesk.models.hand import PixelPoint


NormalizedPoint: TypeAlias = tuple[float, float]


class ControlMode(StrEnum):
    """High-level system-control surface."""

    POINTER = "pointer"
    WINDOW = "window"


class WindowActionMode(StrEnum):
    """Active action within window-control mode."""

    MOVE = "move"
    RESIZE = "resize"


class PointerPhase(StrEnum):
    """Pointer phases shared across system-control backends."""

    IDLE = "idle"
    MOVE = "move"
    CLICK = "click"
    PRESS = "press"
    DRAG = "drag"
    RELEASE = "release"
    LOST = "lost"


@dataclass(slots=True)
class SystemControlState:
    """One frame of backend-agnostic system-control intent."""

    enabled: bool = False
    armed: bool = False
    backend_name: str = "disabled"
    control_mode: ControlMode = ControlMode.POINTER
    window_action_mode: WindowActionMode = WindowActionMode.MOVE
    phase: PointerPhase = PointerPhase.IDLE
    frame_cursor_px: PixelPoint | None = None
    normalized_cursor: NormalizedPoint | None = None
    click_count: int = 0
    button_down: bool = False
    clutch_pose: bool = False
    clutch_engaged: bool = False
    permission_granted: bool | None = None
    target_label: str | None = None
    target_locked: bool = False
    effect_label: str = "System control disabled"
