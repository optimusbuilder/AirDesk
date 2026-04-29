"""Translate gesture state into backend-agnostic system intents."""

from dataclasses import dataclass, field
import math
import time
from typing import Callable

from airdesk.config import SystemControlConfig
from airdesk.models.gesture import GestureState
from airdesk.models.hand import PixelPoint
from airdesk.system.intents import NormalizedPoint, PointerPhase, SystemControlState


@dataclass(slots=True)
class SystemIntentController:
    """Produce pointer-style system intents from the gesture stream."""

    config: SystemControlConfig = field(default_factory=SystemControlConfig)
    enabled: bool = False
    previous_button_down: bool = False
    clutch_engaged: bool = False
    pinch_candidate_since: float | None = None
    previous_output_cursor: NormalizedPoint | None = None
    _dwell_anchor: PixelPoint | None = None
    _dwell_started_at: float | None = None
    _dwell_single_fired: bool = False
    _dwell_cooldown_until: float | None = None
    time_fn: Callable[[], float] = time.monotonic

    def reset(self) -> None:
        """Clear any remembered button state."""
        self.previous_button_down = False
        self.clutch_engaged = False
        self.pinch_candidate_since = None
        self.previous_output_cursor = None
        self._dwell_anchor = None
        self._dwell_started_at = None
        self._dwell_single_fired = False
        self._dwell_cooldown_until = None

    def _get_trackpad_bounds(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        w = self.config.trackpad_width
        h = self.config.trackpad_height
        offset = self.config.trackpad_bottom_offset
        
        x_min = (frame_width - w) // 2
        y_max = frame_height - offset
        y_min = y_max - h
        x_max = x_min + w
        
        return x_min, y_min, x_max, y_max

    def update(
        self,
        gesture_state: GestureState,
        frame_width: int,
        frame_height: int,
    ) -> SystemControlState:
        """Return the current system-control intent for this frame."""
        x_min, y_min, x_max, y_max = self._get_trackpad_bounds(frame_width, frame_height)
        
        if not self.enabled:
            self.reset()
            return SystemControlState(
                trackpad_bounds=(x_min, y_min, x_max, y_max),
            )

        now = self.time_fn()
        cursor = self._active_cursor(gesture_state)
        
        if cursor is None:
            if self.previous_button_down:
                release_cursor = self.previous_output_cursor
                self.reset()
                return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.RELEASE,
                    normalized_cursor=release_cursor,
                    effect_label="Tracking lost - would force button release",
                )
            self.reset()
            return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                enabled=True,
                armed=True,
                phase=PointerPhase.LOST,
                effect_label="Point your index finger in the camera view",
            )

        is_in_trackpad = (x_min <= cursor[0] <= x_max) and (y_min <= cursor[1] <= y_max)
        
        if not is_in_trackpad:
            if self.previous_button_down:
                release_cursor = self.previous_output_cursor
                self.reset()
                return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.RELEASE,
                    normalized_cursor=release_cursor,
                    effect_label="Exited trackpad - forced button release",
                )
            self.reset()
            return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                enabled=True,
                armed=True,
                phase=PointerPhase.IDLE,
                effect_label="Move your finger into the trackpad box to steer",
            )

        self.clutch_engaged = True
        
        norm_x = (cursor[0] - x_min) / max(self.config.trackpad_width, 1)
        norm_y = (cursor[1] - y_min) / max(self.config.trackpad_height, 1)
        norm_x = min(max(norm_x, 0.0), 1.0)
        norm_y = min(max(norm_y, 0.0), 1.0)
        
        if self.previous_output_cursor is not None:
            dx = (norm_x - self.previous_output_cursor[0]) * frame_width
            dy = (norm_y - self.previous_output_cursor[1]) * frame_height
            if math.hypot(dx, dy) < self.config.cursor_deadzone_px:
                norm_x, norm_y = self.previous_output_cursor
        
        tuned_cursor = (norm_x, norm_y)

        if gesture_state.pinch_ended:
            if self.previous_button_down:
                self.previous_button_down = False
                self.pinch_candidate_since = None
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.RELEASE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label="Would release the primary button",
                )
                
        if gesture_state.pinch_active and not self.previous_button_down:
            if self.pinch_candidate_since is None:
                self.pinch_candidate_since = now
            elapsed_ms = int((now - self.pinch_candidate_since) * 1000)
            if elapsed_ms < self.config.pinch_press_delay_ms:
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.MOVE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label="Hold pinch to drag",
                )
            self.previous_button_down = True
            self.pinch_candidate_since = None
            self._reset_dwell(now)
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                enabled=True,
                armed=True,
                phase=PointerPhase.PRESS,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                button_down=True,
                clutch_pose=True,
                clutch_engaged=True,
                effect_label="Would press the primary button to drag",
            )
            
        if gesture_state.pinch_active or self.previous_button_down:
            self.previous_button_down = True
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
                enabled=True,
                armed=True,
                phase=PointerPhase.DRAG,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                button_down=True,
                clutch_pose=True,
                clutch_engaged=True,
                effect_label="Dragging...",
            )

        self.previous_button_down = False
        self.pinch_candidate_since = None
        self.previous_output_cursor = tuned_cursor
        
        dwell_result = self._check_dwell_click(cursor, tuned_cursor, now, (x_min, y_min, x_max, y_max))
        if dwell_result is not None:
            return dwell_result

        dwell_progress = self._dwell_progress(now)

        return SystemControlState(
            trackpad_bounds=(x_min, y_min, x_max, y_max),
            enabled=True,
            armed=True,
            phase=PointerPhase.MOVE,
            frame_cursor_px=cursor,
            normalized_cursor=tuned_cursor,
            button_down=False,
            clutch_pose=True,
            clutch_engaged=True,
            dwell_progress=dwell_progress,
            effect_label=(
                f"Dwell {int(dwell_progress * 100)}%"
                if dwell_progress > 0
                else "Hold still to click, pinch to drag"
            ),
        )

    @staticmethod
    def _active_cursor(gesture_state: GestureState) -> PixelPoint | None:
        if not gesture_state.tracking_stable:
            return None
        return gesture_state.cursor_px

    def _check_dwell_click(
        self,
        cursor: PixelPoint,
        tuned_cursor: NormalizedPoint | None,
        now: float,
        trackpad_bounds: tuple[int, int, int, int],
    ) -> SystemControlState | None:
        if not self.config.dwell_click_enabled:
            return None

        if self._dwell_cooldown_until is not None:
            if now < self._dwell_cooldown_until:
                return None
            self._dwell_cooldown_until = None

        if self._dwell_anchor is None:
            self._dwell_anchor = cursor
            self._dwell_started_at = now
            self._dwell_single_fired = False
            return None

        drift = math.dist(cursor, self._dwell_anchor)
        if drift > self.config.dwell_radius_px:
            self._dwell_anchor = cursor
            self._dwell_started_at = now
            self._dwell_single_fired = False
            return None

        elapsed_ms = (now - self._dwell_started_at) * 1000.0

        if elapsed_ms >= self.config.dwell_double_ms:
            self._reset_dwell(now)
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
                trackpad_bounds=trackpad_bounds,
                enabled=True,
                armed=True,
                phase=PointerPhase.CLICK,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                click_count=2,
                button_down=False,
                clutch_pose=True,
                clutch_engaged=True,
                dwell_progress=1.0,
                effect_label="Dwell double-click",
            )

        if elapsed_ms >= self.config.dwell_single_ms and not self._dwell_single_fired:
            self._dwell_single_fired = True
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
                trackpad_bounds=trackpad_bounds,
                enabled=True,
                armed=True,
                phase=PointerPhase.CLICK,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                click_count=1,
                button_down=False,
                clutch_pose=True,
                clutch_engaged=True,
                dwell_progress=self.config.dwell_single_ms / self.config.dwell_double_ms,
                effect_label="Dwell click",
            )

        return None

    def _dwell_progress(self, now: float) -> float:
        if (
            not self.config.dwell_click_enabled
            or self._dwell_started_at is None
            or self._dwell_cooldown_until is not None
        ):
            return 0.0
        elapsed_ms = (now - self._dwell_started_at) * 1000.0
        return min(elapsed_ms / max(self.config.dwell_double_ms, 1), 1.0)

    def _reset_dwell(self, now: float) -> None:
        self._dwell_anchor = None
        self._dwell_started_at = None
        self._dwell_single_fired = False
        self._dwell_cooldown_until = now + self.config.dwell_cooldown_ms / 1000.0
