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
    clutch_candidate_since: float | None = None
    _clutch_last_true_at: float | None = None
    pinch_candidate_since: float | None = None
    pinch_candidate_cursor: PixelPoint | None = None
    last_click_at: float | None = None
    last_click_cursor: PixelPoint | None = None
    last_click_output_cursor: NormalizedPoint | None = None
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
        self.clutch_candidate_since = None
        self._clutch_last_true_at = None
        self.pinch_candidate_since = None
        self.pinch_candidate_cursor = None
        self.last_click_at = None
        self.last_click_cursor = None
        self.last_click_output_cursor = None
        self.previous_output_cursor = None
        self._dwell_anchor = None
        self._dwell_started_at = None
        self._dwell_single_fired = False
        self._dwell_cooldown_until = None

    def update(
        self,
        gesture_state: GestureState,
        frame_width: int,
        frame_height: int,
    ) -> SystemControlState:
        """Return the current system-control intent for this frame."""
        if not self.enabled:
            self.reset()
            return SystemControlState()

        now = self.time_fn()
        cursor = self._active_cursor(gesture_state)
        normalized_cursor = self._normalize_cursor(cursor, frame_width, frame_height)
        tuned_cursor = self._tune_cursor(normalized_cursor, frame_width, frame_height)

        if cursor is None:
            if self.previous_button_down:
                release_cursor = self.previous_output_cursor
                self.reset()
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.RELEASE,
                    normalized_cursor=release_cursor,
                    effect_label="Tracking lost - would force button release",
                )
            self.reset()
            return SystemControlState(
                enabled=True,
                armed=True,
                phase=PointerPhase.LOST,
                effect_label="Show one open hand to engage control",
            )

        if gesture_state.clutch_pose:
            # Refresh the timestamp every frame the clutch pose is seen.
            self._clutch_last_true_at = now
        else:
            # Clutch pose is False.  Keep the clutch alive for a grace
            # period so the pinch debounce has time to commit before the
            # clutch drops.  Without this, fast pinches would kill the
            # clutch during the ~40 ms debounce window — before
            # pinch_active is True — making clicks impossible.
            pinch_holding = (
                gesture_state.pinch_active
                or gesture_state.pinch_started
                or gesture_state.pinch_ended
            )
            grace_alive = (
                self._clutch_last_true_at is not None
                and (now - self._clutch_last_true_at) * 1000
                    < self.config.clutch_grace_ms
            )
            if not (self.clutch_engaged and (pinch_holding or grace_alive)):
                self.clutch_candidate_since = None
                self.pinch_candidate_since = None
                self._clutch_last_true_at = None
                self._clear_last_click()
                if self.previous_button_down:
                    self.previous_button_down = False
                    self.clutch_engaged = False
                    self.previous_output_cursor = tuned_cursor
                    return SystemControlState(
                        enabled=True,
                        armed=True,
                        phase=PointerPhase.RELEASE,
                        frame_cursor_px=cursor,
                        normalized_cursor=tuned_cursor,
                        button_down=False,
                        clutch_pose=False,
                        clutch_engaged=False,
                        effect_label="Clutch released - would release the primary button",
                    )

                self.clutch_engaged = False
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.IDLE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    button_down=False,
                    clutch_pose=False,
                    clutch_engaged=False,
                    effect_label="Hold an open palm to engage control",
                )

        if not self.clutch_engaged:
            if self.clutch_candidate_since is None:
                self.clutch_candidate_since = now
            elapsed_ms = int((now - self.clutch_candidate_since) * 1000)
            if elapsed_ms < self.config.clutch_activation_ms:
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.IDLE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=False,
                    effect_label="Hold the open palm steady to engage control",
                )

            self.clutch_engaged = True
            self.pinch_candidate_since = None
            self.pinch_candidate_cursor = None

        self.clutch_candidate_since = now

        if gesture_state.pinch_ended:
            if self.previous_button_down:
                self.previous_button_down = False
                self.pinch_candidate_since = None
                self.pinch_candidate_cursor = None
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.RELEASE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    click_count=0,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label="Would release the primary button",
                )
            if self._is_tap_click(cursor, now):
                if gesture_state.pinch_finger == "middle":
                    # Middle-finger pinch → instant double-click.
                    click_cursor = tuned_cursor
                    click_count = 2
                    self._clear_last_click()
                else:
                    click_cursor, click_count = self._resolve_click_output(
                        cursor, tuned_cursor, now,
                    )
                self.pinch_candidate_since = None
                self.pinch_candidate_cursor = None
                self.previous_output_cursor = click_cursor
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.CLICK,
                    frame_cursor_px=cursor,
                    normalized_cursor=click_cursor,
                    click_count=click_count,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label=(
                        "Would double-click the primary button"
                        if click_count == 2
                        else "Would click the primary button"
                    ),
                )
            self.pinch_candidate_since = None
            self.pinch_candidate_cursor = None
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.MOVE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    click_count=0,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label="Clutch engaged - steer with your hand",
                )

        if gesture_state.pinch_active and not self.previous_button_down:
            # Pinch started — cancel any in-progress dwell.
            self._dwell_anchor = None
            self._dwell_started_at = None
            self._dwell_single_fired = False
            if self.pinch_candidate_since is None:
                self.pinch_candidate_since = now
                self.pinch_candidate_cursor = cursor
            elapsed_ms = int((now - self.pinch_candidate_since) * 1000)
            if elapsed_ms < self.config.pinch_press_delay_ms:
                self.previous_output_cursor = tuned_cursor
                return SystemControlState(
                    enabled=True,
                    armed=True,
                    phase=PointerPhase.MOVE,
                    frame_cursor_px=cursor,
                    normalized_cursor=tuned_cursor,
                    click_count=0,
                    button_down=False,
                    clutch_pose=True,
                    clutch_engaged=True,
                    effect_label=(
                        "Middle-finger tap → open file"
                        if gesture_state.pinch_finger == "middle"
                        else "Release to click, hold to drag"
                    ),
                )

            self.previous_button_down = True
            self.pinch_candidate_since = None
            self.pinch_candidate_cursor = None
            self._clear_last_click()
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
                enabled=True,
                armed=True,
                phase=PointerPhase.PRESS,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                click_count=0,
                button_down=True,
                clutch_pose=True,
                clutch_engaged=True,
                effect_label="Would press the primary button",
            )

        if gesture_state.pinch_active or self.previous_button_down:
            self.previous_button_down = True
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
                enabled=True,
                armed=True,
                phase=PointerPhase.DRAG,
                frame_cursor_px=cursor,
                normalized_cursor=tuned_cursor,
                click_count=0,
                button_down=True,
                clutch_pose=True,
                clutch_engaged=True,
                effect_label="Would drag the system pointer",
            )

        self.previous_button_down = False
        self.pinch_candidate_since = None
        self.pinch_candidate_cursor = None
        self.previous_output_cursor = tuned_cursor

        # --- Dwell-click: hold the cursor still to click ---
        dwell_result = self._check_dwell_click(cursor, tuned_cursor, now)
        if dwell_result is not None:
            return dwell_result

        # Compute dwell progress for the visual ring.
        dwell_progress = self._dwell_progress(now)

        return SystemControlState(
            enabled=True,
            armed=True,
            phase=PointerPhase.MOVE,
            frame_cursor_px=cursor,
            normalized_cursor=tuned_cursor,
            click_count=0,
            button_down=False,
            clutch_pose=True,
            clutch_engaged=True,
            dwell_progress=dwell_progress,
            effect_label=(
                f"Dwell {int(dwell_progress * 100)}%"
                if dwell_progress > 0
                else "Hold still to click"
            ),
        )

    def _is_tap_click(self, cursor: PixelPoint | None, now: float) -> bool:
        if (
            cursor is None
            or self.pinch_candidate_since is None
            or self.pinch_candidate_cursor is None
        ):
            return False

        elapsed_ms = (now - self.pinch_candidate_since) * 1000.0
        if elapsed_ms >= self.config.pinch_press_delay_ms:
            return False

        movement_px = math.dist(cursor, self.pinch_candidate_cursor)
        return movement_px <= max(self.config.tap_click_max_movement_px, 0)

    def _resolve_click_output(
        self,
        cursor: PixelPoint,
        tuned_cursor: NormalizedPoint | None,
        now: float,
    ) -> tuple[NormalizedPoint | None, int]:
        if self._is_double_click(cursor, now):
            anchored_cursor = self.last_click_output_cursor or tuned_cursor
            self._clear_last_click()
            return anchored_cursor, 2

        self.last_click_at = now
        self.last_click_cursor = cursor
        self.last_click_output_cursor = tuned_cursor
        return tuned_cursor, 1

    def _is_double_click(self, cursor: PixelPoint, now: float) -> bool:
        if (
            self.last_click_at is None
            or self.last_click_cursor is None
            or self.last_click_output_cursor is None
        ):
            return False

        elapsed_ms = (now - self.last_click_at) * 1000.0
        if elapsed_ms > self.config.double_click_window_ms:
            return False

        movement_px = math.dist(cursor, self.last_click_cursor)
        return movement_px <= max(self.config.double_click_max_movement_px, 0)

    def _clear_last_click(self) -> None:
        self.last_click_at = None
        self.last_click_cursor = None
        self.last_click_output_cursor = None

    @staticmethod
    def _active_cursor(gesture_state: GestureState) -> PixelPoint | None:
        if not gesture_state.tracking_stable:
            return None
        return gesture_state.cursor_px

    @staticmethod
    def _normalize_cursor(
        cursor: PixelPoint | None,
        frame_width: int,
        frame_height: int,
    ) -> NormalizedPoint | None:
        if cursor is None:
            return None

        width = max(frame_width - 1, 1)
        height = max(frame_height - 1, 1)
        return (
            min(max(cursor[0] / width, 0.0), 1.0),
            min(max(cursor[1] / height, 0.0), 1.0),
        )

    def _tune_cursor(
        self,
        cursor: NormalizedPoint | None,
        frame_width: int,
        frame_height: int,
    ) -> NormalizedPoint | None:
        if cursor is None:
            return None

        padded_x = self._apply_edge_padding(cursor[0])
        padded_y = self._apply_edge_padding(cursor[1])
        tuned = (
            self._apply_sensitivity(padded_x),
            self._apply_sensitivity(padded_y),
        )

        if self.previous_output_cursor is None:
            return tuned

        delta_x = (tuned[0] - self.previous_output_cursor[0]) * max(frame_width - 1, 1)
        delta_y = (tuned[1] - self.previous_output_cursor[1]) * max(frame_height - 1, 1)
        if math.hypot(delta_x, delta_y) < self.config.cursor_deadzone_px:
            return self.previous_output_cursor
        return tuned

    def _apply_edge_padding(self, value: float) -> float:
        padding = min(max(self.config.cursor_edge_padding, 0.0), 0.45)
        if padding == 0.0:
            return min(max(value, 0.0), 1.0)
        if value <= padding:
            return 0.0
        if value >= 1.0 - padding:
            return 1.0
        return (value - padding) / (1.0 - (padding * 2.0))

    def _apply_sensitivity(self, value: float) -> float:
        sensitivity = max(self.config.cursor_sensitivity, 0.1)
        centered = (value - 0.5) * sensitivity
        return min(max(centered + 0.5, 0.0), 1.0)

    # ---- Dwell-click ----

    def _check_dwell_click(
        self,
        cursor: PixelPoint,
        tuned_cursor: NormalizedPoint | None,
        now: float,
    ) -> SystemControlState | None:
        """Check if the cursor has been still long enough to fire a click.

        Returns a CLICK state if a dwell threshold is reached, or None to
        let the caller emit a normal MOVE frame.
        """
        if not self.config.dwell_click_enabled:
            return None

        # Still in cooldown from a previous dwell-click?
        if self._dwell_cooldown_until is not None:
            if now < self._dwell_cooldown_until:
                return None
            self._dwell_cooldown_until = None

        # Start a new dwell if there is no anchor.
        if self._dwell_anchor is None:
            self._dwell_anchor = cursor
            self._dwell_started_at = now
            self._dwell_single_fired = False
            return None

        # Check if cursor has drifted beyond the stillness radius.
        drift = math.dist(cursor, self._dwell_anchor)
        if drift > self.config.dwell_radius_px:
            self._dwell_anchor = cursor
            self._dwell_started_at = now
            self._dwell_single_fired = False
            return None

        elapsed_ms = (now - self._dwell_started_at) * 1000.0

        # Double-click threshold (fires second, takes priority).
        if elapsed_ms >= self.config.dwell_double_ms:
            self._reset_dwell(now)
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
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

        # Single-click threshold.
        if elapsed_ms >= self.config.dwell_single_ms and not self._dwell_single_fired:
            self._dwell_single_fired = True
            self.previous_output_cursor = tuned_cursor
            return SystemControlState(
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
        """Return 0.0-1.0 indicating how far the current dwell has progressed."""
        if (
            not self.config.dwell_click_enabled
            or self._dwell_started_at is None
            or self._dwell_cooldown_until is not None
        ):
            return 0.0
        elapsed_ms = (now - self._dwell_started_at) * 1000.0
        return min(elapsed_ms / max(self.config.dwell_double_ms, 1), 1.0)

    def _reset_dwell(self, now: float) -> None:
        """Reset dwell state and start cooldown."""
        self._dwell_anchor = None
        self._dwell_started_at = None
        self._dwell_single_fired = False
        self._dwell_cooldown_until = now + self.config.dwell_cooldown_ms / 1000.0
