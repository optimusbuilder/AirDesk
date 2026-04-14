"""Hand tracking wrapper for MediaPipe Hands."""

from typing import Any

from airdesk.config import TrackingConfig
from airdesk.models.hand import HandState


class HandTracker:
    """Frame-by-frame hand tracker.

    The concrete MediaPipe integration will be implemented in Milestone 2.
    """

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config

    def detect(self, frame: Any) -> HandState:
        """Detect a single hand and return structured state."""
        raise NotImplementedError("HandTracker.detect will be implemented in Milestone 2.")
