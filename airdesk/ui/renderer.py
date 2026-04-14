"""Rendering abstractions for webcam frames and overlays."""

from typing import Any

from airdesk.config import RenderConfig
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HAND_CONNECTIONS, HandState
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow
from airdesk.ui.theme import DEFAULT_THEME, Theme


class Renderer:
    """Owns frame composition for the AirDesk UI."""

    def __init__(self, config: RenderConfig, theme: Theme = DEFAULT_THEME) -> None:
        self.config = config
        self.theme = theme
        self._cv2 = self._load_cv2()

    def render(
        self,
        frame: Any,
        hand_state: HandState,
        gesture_state: GestureState,
        windows: list[VirtualWindow],
        interaction_state: InteractionState,
    ) -> Any:
        """Compose the current frame."""
        composited = frame.copy()
        self._draw_hand_landmarks(composited, hand_state)

        if self.config.show_debug_hud:
            self._draw_debug_hud(composited, hand_state)

        return composited

    def _draw_hand_landmarks(self, frame: Any, hand_state: HandState) -> None:
        if not hand_state.detected:
            return

        for start, end in HAND_CONNECTIONS:
            start_point = hand_state.landmarks_px.get(start)
            end_point = hand_state.landmarks_px.get(end)
            if start_point is None or end_point is None:
                continue

            self._cv2.line(
                frame,
                start_point,
                end_point,
                self.theme.landmark,
                2,
                self._cv2.LINE_AA,
            )

        accent_landmarks = {4, 8}
        for landmark_id, point in hand_state.landmarks_px.items():
            color = self.theme.landmark_accent if landmark_id in accent_landmarks else self.theme.landmark
            radius = 6 if landmark_id in accent_landmarks else 4
            self._cv2.circle(frame, point, radius, color, -1, self._cv2.LINE_AA)

    def _draw_debug_hud(self, frame: Any, hand_state: HandState) -> None:
        lines = [
            f"Hand: {'detected' if hand_state.detected else 'not detected'}",
            f"Confidence: {hand_state.confidence:.2f}",
        ]

        if hand_state.detected and hand_state.index_tip is not None:
            lines.append(f"Index tip: {hand_state.index_tip[0]}, {hand_state.index_tip[1]}")
            lines.append(f"Hand scale: {hand_state.hand_scale:.1f}px")

        for line_number, text in enumerate(lines):
            y = 28 + (line_number * 24)
            self._cv2.putText(
                frame,
                text,
                (16, y),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                self.theme.text,
                2,
                self._cv2.LINE_AA,
            )

    @staticmethod
    def _load_cv2() -> Any:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenCV is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        return cv2
