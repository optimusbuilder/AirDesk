"""Base interfaces for system-control backends."""

from abc import ABC, abstractmethod

from airdesk.system.intents import ControlMode, SystemControlState


class SystemBackend(ABC):
    """Abstract base class for backends that consume system intents."""

    name: str

    @abstractmethod
    def apply(self, state: SystemControlState) -> SystemControlState:
        """Apply one frame of system intent and return the reported state."""

    def reset(self) -> None:
        """Release any backend-held state before shutdown or disarm."""

    def set_control_mode(self, control_mode: ControlMode) -> None:
        """Switch the active control surface for the backend."""

    def toggle_target_lock(self) -> str | None:
        """Toggle a persistent target lock for the active control surface."""
        return None

    def toggle_window_action_mode(self) -> str | None:
        """Toggle the active action used while in window-control mode."""
        return None
