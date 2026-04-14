"""Interaction state models for hover and grab behavior."""

from dataclasses import dataclass


@dataclass(slots=True)
class InteractionState:
    """Tracks hover and drag state between frames."""

    hovered_window_id: str | None = None
    grabbed_window_id: str | None = None
    grab_offset_x: float = 0.0
    grab_offset_y: float = 0.0
    hand_missing_since: float | None = None

    def clear_grab(self) -> None:
        """Reset the active grab state."""
        self.grabbed_window_id = None
        self.grab_offset_x = 0.0
        self.grab_offset_y = 0.0
        self.hand_missing_since = None
