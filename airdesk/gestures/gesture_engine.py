"""Gesture interpretation from tracked hand landmarks."""

from dataclasses import dataclass

from airdesk.config import GestureConfig
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HandState, PixelPoint


@dataclass(slots=True)
class GestureEngine:
    """Converts hand landmarks into higher-level gesture signals."""

    config: GestureConfig
    previous_cursor: PixelPoint | None = None
    previous_pinch_active: bool = False

    def update(self, hand_state: HandState) -> GestureState:
        """Derive gesture state from the tracked hand."""
        raise NotImplementedError("GestureEngine.update will be implemented in Milestone 3.")
