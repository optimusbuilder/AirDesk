"""Camera abstractions for the AirDesk runtime."""

from dataclasses import dataclass
from typing import Any

from airdesk.config import CameraConfig


@dataclass(slots=True)
class CameraFrame:
    """Container for a frame and its metadata."""

    image: Any
    width: int
    height: int
    mirrored: bool = True


class CameraStream:
    """Thin wrapper around webcam capture.

    The concrete OpenCV implementation will be added in Milestone 1.
    """

    def __init__(self, config: CameraConfig) -> None:
        self.config = config

    def open(self) -> None:
        """Open the webcam stream."""
        raise NotImplementedError("CameraStream.open will be implemented in Milestone 1.")

    def read(self) -> CameraFrame:
        """Read the next frame from the webcam."""
        raise NotImplementedError("CameraStream.read will be implemented in Milestone 1.")

    def close(self) -> None:
        """Release any active webcam resources."""
        raise NotImplementedError("CameraStream.close will be implemented in Milestone 1.")
