"""Future macOS backend for real system control."""

from dataclasses import dataclass

from airdesk.platform.base import SystemBackend
from airdesk.system.intents import SystemControlState


@dataclass(slots=True)
class MacOSSystemBackend(SystemBackend):
    """Placeholder for future real macOS pointer and window control."""

    name: str = "macos"

    def apply(self, state: SystemControlState) -> SystemControlState:
        """Raise until the real macOS backend is implemented."""
        raise NotImplementedError(
            "The real macOS backend is not implemented yet. Use `system-shadow` mode first."
        )
