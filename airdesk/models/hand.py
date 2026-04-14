"""Hand tracking state models."""

from dataclasses import dataclass, field
from typing import TypeAlias


PixelPoint: TypeAlias = tuple[int, int]
LandmarkMap: TypeAlias = dict[int, PixelPoint]
HandConnections: TypeAlias = tuple[tuple[int, int], ...]

HAND_CONNECTIONS: HandConnections = (
    (0, 1),
    (1, 5),
    (5, 9),
    (9, 13),
    (13, 17),
    (0, 17),
    (1, 2),
    (2, 3),
    (3, 4),
    (5, 6),
    (6, 7),
    (7, 8),
    (9, 10),
    (10, 11),
    (11, 12),
    (13, 14),
    (14, 15),
    (15, 16),
    (17, 18),
    (18, 19),
    (19, 20),
)


@dataclass(slots=True)
class HandState:
    """Represents the current state of the tracked hand."""

    detected: bool = False
    confidence: float = 0.0
    landmarks_px: LandmarkMap = field(default_factory=dict)
    index_tip: PixelPoint | None = None
    thumb_tip: PixelPoint | None = None
    palm_center: PixelPoint | None = None
    hand_scale: float = 1.0
    last_seen_time: float | None = None
