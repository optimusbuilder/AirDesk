"""Hand tracking wrapper for MediaPipe Hands."""

import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from airdesk.config import TrackingConfig
from airdesk.models.hand import HandState


class HandTracker:
    """Frame-by-frame hand tracker backed by MediaPipe Tasks."""

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config
        self._cv2 = self._load_cv2()
        self._mp = self._load_mediapipe()
        self._hand_landmark = self._load_hand_landmark_enum()
        self._landmarker = self._create_landmarker()
        self._last_timestamp_ms = 0

    def detect(self, frame: Any) -> HandState:
        """Detect a single hand and return structured state."""
        rgb_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(mp_image, self._next_timestamp_ms())
        return self._build_hand_state(result, frame_width=frame.shape[1], frame_height=frame.shape[0])

    def close(self) -> None:
        """Release MediaPipe task resources."""
        if self._landmarker is None:
            return

        self._landmarker.close()
        self._landmarker = None

    @staticmethod
    def _load_cv2() -> Any:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenCV is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        return cv2

    @staticmethod
    def _load_mediapipe() -> Any:
        if "MPLCONFIGDIR" not in os.environ:
            matplotlib_cache_dir = Path(tempfile.gettempdir()) / "airdesk-mpl"
            matplotlib_cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["MPLCONFIGDIR"] = str(matplotlib_cache_dir)

        try:
            import mediapipe as mp
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "MediaPipe is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        return mp

    @staticmethod
    def _load_hand_landmark_enum() -> Any:
        try:
            from mediapipe.tasks.python.vision.hand_landmarker import HandLandmark
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "MediaPipe hand landmark support is unavailable in this environment."
            ) from exc

        return HandLandmark

    def _create_landmarker(self) -> Any:
        model_path = Path(self.config.model_asset_path)
        if not model_path.exists():
            raise RuntimeError(
                f"Hand landmarker model not found at {model_path}. "
                "Download the model bundle before launching AirDesk."
            )

        options = self._mp.tasks.vision.HandLandmarkerOptions(
            base_options=self._mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=self._mp.tasks.vision.RunningMode.VIDEO,
            num_hands=self.config.max_num_hands,
            min_hand_detection_confidence=self.config.min_detection_confidence,
            min_hand_presence_confidence=self.config.min_hand_presence_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )
        try:
            return self._mp.tasks.vision.HandLandmarker.create_from_options(options)
        except RuntimeError as exc:
            message = str(exc)
            if "NSOpenGLPixelFormat" in message or "kGpuService" in message:
                raise RuntimeError(
                    "MediaPipe could not initialize its graphics services. "
                    "Launch AirDesk from a local GUI-enabled macOS session with "
                    "camera/display access, and use Python 3.11 or 3.12."
                ) from exc
            raise

    def _next_timestamp_ms(self) -> int:
        timestamp_ms = int(time.monotonic() * 1000)
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms
        return timestamp_ms

    def _build_hand_state(self, result: Any, frame_width: int, frame_height: int) -> HandState:
        hand_index = self._select_primary_hand_index(result)
        if hand_index is None:
            return HandState()

        landmarks = result.hand_landmarks[hand_index]
        landmarks_px = {
            index: (
                self._clamp(round(landmark.x * (frame_width - 1)), upper=frame_width - 1),
                self._clamp(round(landmark.y * (frame_height - 1)), upper=frame_height - 1),
            )
            for index, landmark in enumerate(landmarks)
        }

        thumb_tip_id = int(self._hand_landmark.THUMB_TIP)
        index_tip_id = int(self._hand_landmark.INDEX_FINGER_TIP)

        return HandState(
            detected=True,
            confidence=self._extract_confidence(result, hand_index),
            landmarks_px=landmarks_px,
            index_tip=landmarks_px.get(index_tip_id),
            thumb_tip=landmarks_px.get(thumb_tip_id),
            palm_center=self._compute_palm_center(landmarks_px),
            hand_scale=self._compute_hand_scale(landmarks_px),
            last_seen_time=time.monotonic(),
        )

    def _select_primary_hand_index(self, result: Any) -> int | None:
        if not result.hand_landmarks:
            return None

        best_index = 0
        best_score = -1.0
        for index, handedness_list in enumerate(result.handedness):
            score = handedness_list[0].score if handedness_list else 0.0
            if score > best_score:
                best_index = index
                best_score = score

        return best_index

    def _extract_confidence(self, result: Any, hand_index: int) -> float:
        if hand_index >= len(result.handedness) or not result.handedness[hand_index]:
            return 0.0
        return float(result.handedness[hand_index][0].score)

    def _compute_palm_center(self, landmarks_px: dict[int, tuple[int, int]]) -> tuple[int, int] | None:
        palm_landmark_ids = (
            int(self._hand_landmark.WRIST),
            int(self._hand_landmark.INDEX_FINGER_MCP),
            int(self._hand_landmark.MIDDLE_FINGER_MCP),
            int(self._hand_landmark.RING_FINGER_MCP),
            int(self._hand_landmark.PINKY_MCP),
        )
        palm_points = [landmarks_px[landmark_id] for landmark_id in palm_landmark_ids]
        return (
            round(sum(point[0] for point in palm_points) / len(palm_points)),
            round(sum(point[1] for point in palm_points) / len(palm_points)),
        )

    def _compute_hand_scale(self, landmarks_px: dict[int, tuple[int, int]]) -> float:
        index_mcp = landmarks_px[int(self._hand_landmark.INDEX_FINGER_MCP)]
        pinky_mcp = landmarks_px[int(self._hand_landmark.PINKY_MCP)]
        return max(math.dist(index_mcp, pinky_mcp), 1.0)

    @staticmethod
    def _clamp(value: int, upper: int) -> int:
        return min(max(value, 0), upper)
