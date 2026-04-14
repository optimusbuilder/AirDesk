"""Rendering abstractions for webcam frames and overlays."""

import math
from typing import Any

from airdesk.config import RenderConfig
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HAND_CONNECTIONS, HandState
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow, WindowState
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
        self._draw_windows(composited, windows)
        self._draw_cursor(composited, gesture_state)
        self._draw_hand_landmarks(composited, hand_state)

        if self.config.show_debug_hud:
            self._draw_debug_hud(composited, hand_state, gesture_state, interaction_state)

        return composited

    def _draw_windows(self, frame: Any, windows: list[VirtualWindow]) -> None:
        for window in windows:
            self._draw_window_shadow(frame, window)
            self._draw_window_fill(frame, window)
            self._draw_window_border(frame, window)
            self._draw_window_text(frame, window)

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

    def _draw_cursor(self, frame: Any, gesture_state: GestureState) -> None:
        cursor = gesture_state.cursor_px
        if cursor is None or not gesture_state.tracking_stable:
            return

        outer_radius = self.config.cursor_radius
        inner_radius = max(self.config.cursor_radius // 3, 2)
        cursor_color = self.theme.landmark_accent if gesture_state.pinch_active else self.theme.cursor
        thickness = 3 if gesture_state.pinch_active else 2
        self._cv2.circle(
            frame,
            cursor,
            outer_radius,
            cursor_color,
            thickness,
            self._cv2.LINE_AA,
        )
        self._cv2.circle(
            frame,
            cursor,
            inner_radius,
            cursor_color,
            -1,
            self._cv2.LINE_AA,
        )

    def _draw_window_shadow(self, frame: Any, window: VirtualWindow) -> None:
        shadow_alpha = 0.24
        shadow_offset = 8
        self._draw_translucent_rect(
            frame,
            x=window.x + shadow_offset,
            y=window.y + shadow_offset,
            width=window.width,
            height=window.height,
            color=self.theme.panel_shadow,
            alpha=shadow_alpha,
        )

    def _draw_window_fill(self, frame: Any, window: VirtualWindow) -> None:
        if window.state is WindowState.GRABBED:
            fill_alpha = 0.60
            header_alpha = 0.44
        elif window.state is WindowState.HOVERED:
            fill_alpha = 0.54
            header_alpha = 0.38
        else:
            fill_alpha = 0.42
            header_alpha = 0.30
        header_height = 34
        self._draw_translucent_rect(
            frame,
            x=window.x,
            y=window.y,
            width=window.width,
            height=window.height,
            color=self.theme.panel_fill,
            alpha=fill_alpha,
        )
        self._draw_translucent_rect(
            frame,
            x=window.x,
            y=window.y,
            width=window.width,
            height=header_height,
            color=self._accent_for_window(window),
            alpha=header_alpha,
        )

    def _draw_window_border(self, frame: Any, window: VirtualWindow) -> None:
        border_color = self._border_for_window(window)
        if window.state is WindowState.GRABBED:
            thickness = self.config.window_border_thickness + 2
        elif window.state is WindowState.HOVERED:
            thickness = self.config.window_border_thickness + 1
        else:
            thickness = self.config.window_border_thickness
        self._cv2.rectangle(
            frame,
            (window.x, window.y),
            (window.x + window.width, window.y + window.height),
            border_color,
            thickness,
            self._cv2.LINE_AA,
        )

        header_y = window.y + 34
        self._cv2.line(
            frame,
            (window.x, header_y),
            (window.x + window.width, header_y),
            border_color,
            1,
            self._cv2.LINE_AA,
        )

    def _draw_window_text(self, frame: Any, window: VirtualWindow) -> None:
        title_color = self._border_for_window(window)
        self._cv2.putText(
            frame,
            window.title,
            (window.x + 14, window.y + 23),
            self._cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            title_color,
            2,
            self._cv2.LINE_AA,
        )

        body_lines = window.body_lines or ("Virtual panel ready",)
        for index, line in enumerate(body_lines):
            self._cv2.putText(
                frame,
                line,
                (window.x + 14, window.y + 60 + (index * 24)),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                self.theme.text,
                1,
                self._cv2.LINE_AA,
            )

    def _draw_debug_hud(
        self,
        frame: Any,
        hand_state: HandState,
        gesture_state: GestureState,
        interaction_state: InteractionState,
    ) -> None:
        lines = [
            f"Hand: {'detected' if hand_state.detected else 'not detected'}",
            f"Confidence: {hand_state.confidence:.2f}",
            f"Tracking: {'stable' if gesture_state.tracking_stable else 'lost'}",
            f"Pinch: {'active' if gesture_state.pinch_active else 'idle'}",
            f"Hovered window: {interaction_state.hovered_window_id or 'none'}",
            f"Grabbed window: {interaction_state.grabbed_window_id or 'none'}",
        ]

        if hand_state.detected and hand_state.index_tip is not None:
            lines.append(f"Index tip: {hand_state.index_tip[0]}, {hand_state.index_tip[1]}")
            lines.append(f"Hand scale: {hand_state.hand_scale:.1f}px")

        if gesture_state.raw_cursor_px is not None:
            lines.append(
                f"Raw cursor: {gesture_state.raw_cursor_px[0]}, {gesture_state.raw_cursor_px[1]}"
            )

        if gesture_state.cursor_px is not None:
            lines.append(f"Cursor: {gesture_state.cursor_px[0]}, {gesture_state.cursor_px[1]}")

        if math.isfinite(gesture_state.pinch_ratio):
            lines.append(f"Pinch ratio: {gesture_state.pinch_ratio:.3f}")
        elif hand_state.detected:
            lines.append("Pinch ratio: n/a")

        if gesture_state.pinch_started:
            lines.append("Pinch event: started")
        elif gesture_state.pinch_ended:
            lines.append("Pinch event: ended")

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

    def _draw_translucent_rect(
        self,
        frame: Any,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[int, int, int],
        alpha: float,
    ) -> None:
        overlay = frame.copy()
        self._cv2.rectangle(
            overlay,
            (x, y),
            (x + width, y + height),
            color,
            -1,
            self._cv2.LINE_AA,
        )
        self._cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0.0, frame)

    def _border_for_window(self, window: VirtualWindow) -> tuple[int, int, int]:
        if window.state is WindowState.GRABBED:
            return self.theme.panel_grabbed_border
        if window.state is WindowState.HOVERED:
            return self.theme.panel_hover_border
        return self.theme.panel_border

    def _accent_for_window(self, window: VirtualWindow) -> tuple[int, int, int]:
        if window.state is WindowState.GRABBED:
            return self.theme.panel_grabbed_border
        if window.state is WindowState.HOVERED:
            return self.theme.panel_hover_border
        return self.theme.panel_border

    @staticmethod
    def _load_cv2() -> Any:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenCV is not installed. Install project dependencies before launching AirDesk."
            ) from exc

        return cv2
