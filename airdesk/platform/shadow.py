"""Shadow backend that reports intended system actions without executing them."""

from dataclasses import dataclass

from airdesk.platform.base import SystemBackend
from airdesk.system.intents import (
    ControlMode,
    PointerPhase,
    SystemControlState,
    WindowActionMode,
)


@dataclass(slots=True)
class ShadowSystemBackend(SystemBackend):
    """Safe backend that reports what AirDesk would do to the OS."""

    name: str = "shadow"
    control_mode: ControlMode = ControlMode.POINTER
    window_action_mode: WindowActionMode = WindowActionMode.MOVE
    locked_target_label: str | None = None

    def apply(self, state: SystemControlState) -> SystemControlState:
        """Annotate the state with a backend name and human-readable action."""
        state.backend_name = self.name
        state.control_mode = self.control_mode
        state.window_action_mode = self.window_action_mode
        if self.locked_target_label is not None and state.target_label is None:
            state.target_label = self.locked_target_label
        state.target_locked = self.locked_target_label is not None
        state.effect_label = self._describe(state)
        return state

    def set_control_mode(self, control_mode: ControlMode) -> None:
        """Switch between pointer and window-preview descriptions."""
        self.control_mode = control_mode

    def toggle_target_lock(self) -> str | None:
        """Toggle a shadow target lock for window-mode previews."""
        if self.control_mode is not ControlMode.WINDOW:
            return "Switch to window mode before locking a target."
        if self.locked_target_label is not None:
            title = self.locked_target_label
            self.locked_target_label = None
            return f'Cleared locked window target "{title}".'
        self.locked_target_label = "Focused window"
        return f'Locked "{self.locked_target_label}" as the window target.'

    def toggle_window_action_mode(self) -> str | None:
        """Toggle between move and resize previews while in window mode."""
        if self.control_mode is not ControlMode.WINDOW:
            return "Switch to window mode before changing the window action."
        next_mode = (
            WindowActionMode.RESIZE
            if self.window_action_mode is WindowActionMode.MOVE
            else WindowActionMode.MOVE
        )
        self.window_action_mode = next_mode
        return f"Window action switched to {next_mode.value}."

    def _describe(self, state: SystemControlState) -> str:
        if self.control_mode is ControlMode.WINDOW:
            return self._describe_window_mode(state)
        if state.phase is PointerPhase.LOST:
            return state.effect_label
        if state.phase is PointerPhase.RELEASE and state.frame_cursor_px is None:
            return "Shadow mode would release after tracking loss"
        if state.phase is PointerPhase.IDLE:
            return state.effect_label
        if state.frame_cursor_px is None:
            return state.effect_label

        x, y = state.frame_cursor_px
        if state.phase is PointerPhase.CLICK:
            if state.click_count == 2:
                return f"Shadow double-click at {x}, {y}"
            return f"Shadow click at {x}, {y}"
        if state.phase is PointerPhase.PRESS:
            return f"Shadow press at {x}, {y}"
        if state.phase is PointerPhase.DRAG:
            return f"Shadow drag through {x}, {y}"
        if state.phase is PointerPhase.RELEASE:
            return f"Shadow release at {x}, {y}"
        if state.phase is PointerPhase.MOVE:
            return f"Shadow move to {x}, {y}"
        return "Shadow mode idle"

    def _describe_window_mode(self, state: SystemControlState) -> str:
        if state.phase is PointerPhase.LOST:
            return "Shadow window mode waiting for one tracked hand"
        if state.phase is PointerPhase.IDLE:
            return state.effect_label
        action_label = (
            "resize"
            if self.window_action_mode is WindowActionMode.RESIZE
            else "move"
        )
        if state.phase is PointerPhase.PRESS:
            return f"Shadow would grab the focused window for {action_label}"
        if state.phase is PointerPhase.CLICK:
            if state.click_count == 2:
                return "Shadow would ignore a quick double tap in window mode"
            return "Shadow would ignore a quick tap in window mode"
        if state.phase is PointerPhase.DRAG:
            if self.window_action_mode is WindowActionMode.RESIZE:
                return "Shadow would resize the focused window"
            return "Shadow would move or snap the focused window"
        if state.phase is PointerPhase.RELEASE:
            if self.window_action_mode is WindowActionMode.RESIZE:
                return "Shadow would release the resized window"
            return "Shadow would release or snap the focused window"
        if state.target_locked and state.target_label is not None:
            return (
                f'Shadow window mode locked to "{state.target_label}" '
                f"for {action_label}"
            )
        return f"Shadow window mode ready to {action_label} the focused window"
