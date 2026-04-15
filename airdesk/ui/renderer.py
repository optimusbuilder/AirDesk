"""Rendering abstractions for webcam frames and overlays."""

import math
from typing import Any

from airdesk.config import AppMode, RenderConfig
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HAND_CONNECTIONS, HandState
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow, WindowState
from airdesk.system.intents import SystemControlState
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
        system_state: SystemControlState | None = None,
        app_mode: AppMode = AppMode.PROTOTYPE,
    ) -> Any:
        """Compose the current frame."""
        composited = frame.copy()
        self._draw_windows(composited, windows)
        self._draw_cursor(composited, gesture_state)
        self._draw_hand_landmarks(composited, hand_state)
        self._draw_status_chip(
            composited,
            gesture_state,
            interaction_state,
            system_state or SystemControlState(),
            app_mode,
        )

        if self.config.show_debug_hud:
            self._draw_debug_hud(
                composited,
                hand_state,
                gesture_state,
                interaction_state,
                system_state or SystemControlState(),
                app_mode,
            )

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
        if window.state is WindowState.GRABBED:
            shadow_alpha = 0.34
            shadow_offset = 12
        elif window.state is WindowState.HOVERED:
            shadow_alpha = 0.28
            shadow_offset = 10
        else:
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
        title_font_scale = 0.54
        title_thickness = 2
        body_font_scale = 0.44
        body_thickness = 1
        body_line_height = 20
        body_left = window.x + 14
        body_top = window.y + 58
        body_width = max(window.width - 28, 40)
        body_height = max(window.height - 72, body_line_height)

        title_color = self._border_for_window(window)
        dots = [
            self.theme.panel_border,
            self.theme.panel_hover_border,
            self.theme.panel_grabbed_border,
        ]
        for index, color in enumerate(dots):
            self._cv2.circle(
                frame,
                (window.x + window.width - 18 - (index * 14), window.y + 18),
                4,
                color,
                -1,
                self._cv2.LINE_AA,
            )

        self._cv2.putText(
            frame,
            window.title,
            (window.x + 14, window.y + 23),
            self._cv2.FONT_HERSHEY_SIMPLEX,
            title_font_scale,
            title_color,
            title_thickness,
            self._cv2.LINE_AA,
        )

        wrapped_lines = self._wrap_block(
            lines=window.body_lines or ("Virtual panel ready",),
            max_width=body_width,
            font_scale=body_font_scale,
            thickness=body_thickness,
        )
        visible_lines = self._fit_lines_to_height(
            lines=wrapped_lines,
            max_height=body_height,
            line_height=body_line_height,
            max_width=body_width,
            font_scale=body_font_scale,
            thickness=body_thickness,
        )

        for index, line in enumerate(visible_lines):
            self._cv2.putText(
                frame,
                line,
                (body_left, body_top + (index * body_line_height)),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                body_font_scale,
                self.theme.text,
                body_thickness,
                self._cv2.LINE_AA,
            )

    def _draw_status_chip(
        self,
        frame: Any,
        gesture_state: GestureState,
        interaction_state: InteractionState,
        system_state: SystemControlState,
        app_mode: AppMode,
    ) -> None:
        chip_width = 248
        chip_height = 92
        margin = 18
        chip_x = max(frame.shape[1] - chip_width - margin, margin)
        chip_y = margin
        self._draw_translucent_rect(
            frame,
            x=chip_x,
            y=chip_y,
            width=chip_width,
            height=chip_height,
            color=self.theme.panel_fill,
            alpha=0.44,
        )
        self._cv2.rectangle(
            frame,
            (chip_x, chip_y),
            (chip_x + chip_width, chip_y + chip_height),
            self.theme.panel_border,
            1,
            self._cv2.LINE_AA,
        )

        if app_mode is AppMode.SYSTEM_SHADOW:
            title = "System Shadow"
            helper = "Point to move, pinch to press"
            status = system_state.effect_label
            status_color = self._color_for_system_phase(system_state)
        else:
            title = "Prototype"
            helper = "Point to hover, pinch to drag"
            if interaction_state.grabbed_window_id is not None:
                status = f"Dragging {interaction_state.grabbed_window_id}"
                status_color = self.theme.panel_grabbed_border
            elif interaction_state.hovered_window_id is not None:
                status = f"Hovering {interaction_state.hovered_window_id}"
                status_color = self.theme.panel_hover_border
            elif gesture_state.tracking_stable:
                status = "Hand tracked"
                status_color = self.theme.cursor
            else:
                status = "Show one hand to begin"
                status_color = self.theme.text

        lines = [title, helper, status]

        for index, line in enumerate(lines):
            color = status_color if index == len(lines) - 1 else self.theme.text
            self._cv2.putText(
                frame,
                line,
                (chip_x + 14, chip_y + 26 + (index * 24)),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                0.54 if index < 2 else 0.5,
                color,
                2 if index == len(lines) - 1 else 1,
                self._cv2.LINE_AA,
            )

    def _draw_debug_hud(
        self,
        frame: Any,
        hand_state: HandState,
        gesture_state: GestureState,
        interaction_state: InteractionState,
        system_state: SystemControlState,
        app_mode: AppMode,
    ) -> None:
        font_scale = 0.46
        thickness = 1
        line_height = 18
        padding_x = 12
        padding_y = 12
        title = "Debug HUD"
        lines = [
            f"Mode: {app_mode.value}",
            f"Hand: {'detected' if hand_state.detected else 'missing'}",
            f"Conf: {hand_state.confidence:.2f}",
            f"Track: {'stable' if gesture_state.tracking_stable else 'lost'}",
            f"Pinch: {'active' if gesture_state.pinch_active else 'idle'}",
            f"Hover: {interaction_state.hovered_window_id or '-'}",
            f"Grab: {interaction_state.grabbed_window_id or '-'}",
        ]

        if system_state.enabled:
            lines.append(f"System: {system_state.phase.value}")
            lines.append(f"Backend: {system_state.backend_name}")

        if gesture_state.cursor_px is not None:
            lines.append(f"Cursor: {gesture_state.cursor_px[0]}, {gesture_state.cursor_px[1]}")

        if math.isfinite(gesture_state.pinch_ratio):
            lines.append(f"Ratio: {gesture_state.pinch_ratio:.3f}")

        content_width = max(
            self._measure_text(title, font_scale=0.5, thickness=2)[0],
            *(self._measure_text(line, font_scale=font_scale, thickness=thickness)[0] for line in lines),
        )
        card_width = content_width + (padding_x * 2)
        card_height = 30 + (len(lines) * line_height) + padding_y
        card_x = 18
        card_y = 18

        self._draw_translucent_rect(
            frame,
            x=card_x,
            y=card_y,
            width=card_width,
            height=card_height,
            color=self.theme.panel_fill,
            alpha=0.48,
        )
        self._cv2.rectangle(
            frame,
            (card_x, card_y),
            (card_x + card_width, card_y + card_height),
            self.theme.panel_border,
            1,
            self._cv2.LINE_AA,
        )
        self._cv2.putText(
            frame,
            title,
            (card_x + padding_x, card_y + 20),
            self._cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            self.theme.panel_hover_border,
            2,
            self._cv2.LINE_AA,
        )

        for line_number, text in enumerate(lines):
            y = card_y + 42 + (line_number * line_height)
            self._cv2.putText(
                frame,
                text,
                (card_x + padding_x, y),
                self._cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                self.theme.text,
                thickness,
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

    def _color_for_system_phase(self, system_state: SystemControlState) -> tuple[int, int, int]:
        if system_state.phase.value in {"press", "drag"}:
            return self.theme.panel_grabbed_border
        if system_state.phase.value == "move":
            return self.theme.cursor
        if system_state.phase.value == "release":
            return self.theme.panel_hover_border
        return self.theme.text

    def _wrap_block(
        self,
        *,
        lines: tuple[str, ...],
        max_width: int,
        font_scale: float,
        thickness: int,
    ) -> list[str]:
        wrapped_lines: list[str] = []
        for line in lines:
            wrapped_lines.extend(
                self._wrap_text(
                    text=line,
                    max_width=max_width,
                    font_scale=font_scale,
                    thickness=thickness,
                )
            )
        return wrapped_lines

    def _wrap_text(
        self,
        *,
        text: str,
        max_width: int,
        font_scale: float,
        thickness: int,
    ) -> list[str]:
        words = text.split()
        if not words:
            return [""]

        wrapped: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            candidate_width, _ = self._measure_text(
                candidate,
                font_scale=font_scale,
                thickness=thickness,
            )
            if candidate_width <= max_width:
                current = candidate
            else:
                wrapped.append(current)
                current = word

        wrapped.append(current)
        return wrapped

    def _fit_lines_to_height(
        self,
        *,
        lines: list[str],
        max_height: int,
        line_height: int,
        max_width: int,
        font_scale: float,
        thickness: int,
    ) -> list[str]:
        max_lines = max(max_height // line_height, 1)
        if len(lines) <= max_lines:
            return lines

        clipped = lines[:max_lines]
        clipped[-1] = self._ellipsize_text(
            text=clipped[-1],
            max_width=max_width,
            font_scale=font_scale,
            thickness=thickness,
        )
        return clipped

    def _ellipsize_text(
        self,
        *,
        text: str,
        max_width: int,
        font_scale: float,
        thickness: int,
    ) -> str:
        candidate = text.rstrip()
        ellipsis = "..."
        while candidate:
            width, _ = self._measure_text(
                f"{candidate}{ellipsis}",
                font_scale=font_scale,
                thickness=thickness,
            )
            if width <= max_width:
                return f"{candidate}{ellipsis}"
            candidate = candidate[:-1].rstrip()
        return ellipsis

    def _measure_text(
        self,
        text: str,
        *,
        font_scale: float,
        thickness: int,
    ) -> tuple[int, int]:
        (width, height), _ = self._cv2.getTextSize(
            text,
            self._cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness,
        )
        return width, height

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
