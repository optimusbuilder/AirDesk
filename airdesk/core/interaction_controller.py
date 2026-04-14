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
        raise NotImplementedError(
            "InteractionController.update will be implemented during the window interaction milestones."
        )
