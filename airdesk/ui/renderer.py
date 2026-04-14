"""Rendering abstractions for webcam frames and overlays."""

from typing import Any

from airdesk.models.gesture import GestureState
from airdesk.models.hand import HandState
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow
from airdesk.ui.theme import DEFAULT_THEME, Theme


class Renderer:
    """Owns frame composition for the AirDesk UI."""

    def __init__(self, theme: Theme = DEFAULT_THEME) -> None:
        self.theme = theme

    def render(
        self,
        frame: Any,
        hand_state: HandState,
        gesture_state: GestureState,
        windows: list[VirtualWindow],
        interaction_state: InteractionState,
    ) -> Any:
        """Compose the current frame.

        Concrete OpenCV drawing code will be added incrementally beginning with
        landmark overlays in Milestone 2.
        """
        raise NotImplementedError("Renderer.render will be implemented in the rendering milestones.")
