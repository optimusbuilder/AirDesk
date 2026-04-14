"""Interaction logic for hover, grab, and release behavior."""

from dataclasses import dataclass

from airdesk.models.gesture import GestureState
from airdesk.models.interaction import InteractionState
from airdesk.core.window_manager import WindowManager


@dataclass(slots=True)
class InteractionController:
    """Coordinates gesture input with window interactions."""

    def update(
        self,
        gesture_state: GestureState,
        window_manager: WindowManager,
        interaction_state: InteractionState,
    ) -> InteractionState:
        """Advance interaction state by one frame."""
        hovered_window_id: str | None = None
        if gesture_state.tracking_stable and gesture_state.cursor_px is not None:
            hovered_window = window_manager.hit_test(gesture_state.cursor_px)
            if hovered_window is not None:
                hovered_window_id = hovered_window.id

        interaction_state.hovered_window_id = hovered_window_id
        window_manager.update_window_states(
            hovered_window_id=hovered_window_id,
            grabbed_window_id=interaction_state.grabbed_window_id,
        )
        return interaction_state
