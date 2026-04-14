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
    """Thin wrapper around webcam capture."""

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._capture: Any | None = None

    def open(self) -> None:
        """Open the webcam stream."""
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenCV is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        if self._capture is not None and self._capture.isOpened():
            return

        capture = cv2.VideoCapture(self.config.device_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)

        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open webcam device {self.config.device_index}.")

        self._capture = capture

    def read(self) -> CameraFrame:
        """Read the next frame from the webcam."""
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenCV is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        if self._capture is None or not self._capture.isOpened():
            raise RuntimeError("Camera stream is not open.")

        success, frame = self._capture.read()
        if not success or frame is None:
            raise RuntimeError("Failed to read frame from webcam.")

        if self.config.mirror_output:
            frame = cv2.flip(frame, 1)

        height, width = frame.shape[:2]
        return CameraFrame(
            image=frame,
            width=width,
            height=height,
            mirrored=self.config.mirror_output,
        )

    def close(self) -> None:
        """Release any active webcam resources."""
        if self._capture is None:
            return

        if self._capture.isOpened():
            self._capture.release()

        self._capture = None
