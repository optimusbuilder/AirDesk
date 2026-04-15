"""Shadow backend that reports intended system actions without executing them."""

from dataclasses import dataclass

from airdesk.platform.base import SystemBackend
from airdesk.system.intents import PointerPhase, SystemControlState


@dataclass(slots=True)
class ShadowSystemBackend(SystemBackend):
    """Safe backend that reports what AirDesk would do to the OS."""

    name: str = "shadow"

    def apply(self, state: SystemControlState) -> SystemControlState:
        """Annotate the state with a backend name and human-readable action."""
        state.backend_name = self.name
        state.effect_label = self._describe(state)
        return state

    def _describe(self, state: SystemControlState) -> str:
        if state.phase is PointerPhase.LOST:
            return "Shadow mode waiting for one tracked hand"
        if state.phase is PointerPhase.RELEASE and state.frame_cursor_px is None:
            return "Shadow mode would release after tracking loss"
        if state.frame_cursor_px is None:
            return "Shadow mode idle"

        x, y = state.frame_cursor_px
        if state.phase is PointerPhase.PRESS:
            return f"Shadow press at {x}, {y}"
        if state.phase is PointerPhase.DRAG:
            return f"Shadow drag through {x}, {y}"
        if state.phase is PointerPhase.RELEASE:
            return f"Shadow release at {x}, {y}"
        if state.phase is PointerPhase.MOVE:
            return f"Shadow move to {x}, {y}"
        return "Shadow mode idle"
