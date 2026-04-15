"""Base interfaces for system-control backends."""

from abc import ABC, abstractmethod

from airdesk.system.intents import SystemControlState


class SystemBackend(ABC):
    """Abstract base class for backends that consume system intents."""

    name: str

    @abstractmethod
    def apply(self, state: SystemControlState) -> SystemControlState:
        """Apply one frame of system intent and return the reported state."""
