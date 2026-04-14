"""Virtual window models used by the in-app compositor."""

from dataclasses import dataclass
from enum import StrEnum

from airdesk.models.hand import PixelPoint


class WindowState(StrEnum):
    """Render states for a virtual window."""

    IDLE = "idle"
    HOVERED = "hovered"
    GRABBED = "grabbed"


@dataclass(slots=True)
class VirtualWindow:
    """Represents a draggable virtual window in pixel space."""

    id: str
    title: str
    x: int
    y: int
    width: int
    height: int
    body_lines: tuple[str, ...] = ()
    z_index: int = 0
    state: WindowState = WindowState.IDLE

    def contains(self, point: PixelPoint) -> bool:
        """Return True when a point is within the window bounds."""
        px, py = point
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def move_to(self, x: int, y: int) -> None:
        """Move the window to a new top-left position."""
        self.x = x
        self.y = y

    def clamp_within(self, bounds_width: int, bounds_height: int) -> None:
        """Keep the window fully inside the visible frame."""
        max_x = max(bounds_width - self.width, 0)
        max_y = max(bounds_height - self.height, 0)
        self.x = min(max(self.x, 0), max_x)
        self.y = min(max(self.y, 0), max_y)
