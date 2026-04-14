"""Hand tracking state models."""

from dataclasses import dataclass, field
from typing import TypeAlias


PixelPoint: TypeAlias = tuple[int, int]
LandmarkMap: TypeAlias = dict[int, PixelPoint]


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
