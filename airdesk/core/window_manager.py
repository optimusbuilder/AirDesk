"""State container and helpers for virtual windows."""

from dataclasses import dataclass, field

from airdesk.models.hand import PixelPoint
from airdesk.models.window import VirtualWindow, WindowState


@dataclass(slots=True)
class WindowManager:
    """Maintains window storage, lookup, and z-order behavior."""

    windows: list[VirtualWindow] = field(default_factory=list)

    def add_window(self, window: VirtualWindow) -> None:
        """Add a new window to the manager."""
        self.windows.append(window)

    def ordered_windows(self) -> list[VirtualWindow]:
        """Return windows sorted back to front."""
        return sorted(self.windows, key=lambda window: window.z_index)

    def hit_test(self, point: PixelPoint) -> VirtualWindow | None:
        """Return the topmost window under the given point."""
        for window in reversed(self.ordered_windows()):
            if window.contains(point):
                return window
        return None

    def get_window(self, window_id: str) -> VirtualWindow | None:
        """Return a window by id."""
        for window in self.windows:
            if window.id == window_id:
                return window
        return None

    def bring_to_front(self, window_id: str) -> VirtualWindow | None:
        """Raise the target window above all others."""
        window = self.get_window(window_id)
        if window is None:
            return None

        next_z_index = max((item.z_index for item in self.windows), default=-1) + 1
        window.z_index = next_z_index
        return window

    def update_window_states(
        self,
        hovered_window_id: str | None,
        grabbed_window_id: str | None,
    ) -> None:
        """Apply visual state flags to all managed windows."""
        for window in self.windows:
            if grabbed_window_id is not None and window.id == grabbed_window_id:
                window.state = WindowState.GRABBED
            elif hovered_window_id is not None and window.id == hovered_window_id:
                window.state = WindowState.HOVERED
            else:
                window.state = WindowState.IDLE
