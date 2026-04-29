"""Gesture interpretation from tracked hand landmarks."""

from dataclasses import dataclass, field
import math
import time
from typing import Callable

from airdesk.config import GestureConfig
from airdesk.gestures.filters import OneEuroFilter
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HandState, PixelPoint


_CLUTCH_FINGER_PAIRS = (
    (5, 8),
    (9, 12),
    (13, 16),
    (17, 20),
)

_MIDDLE_FINGER_TIP_ID = 12


@dataclass(slots=True)
class GestureEngine:
    """Converts hand landmarks into higher-level gesture signals."""

    config: GestureConfig
    _cursor_filter: OneEuroFilter | None = field(default=None, init=False)
    previous_pinch_active: bool = False
    _pending_pinch_state: bool = False
    _pinch_state_since: float | None = field(default=None, init=False)
    _active_pinch_finger: str | None = field(default=None, init=False)
    _time_fn: Callable[[], float] = field(default=time.monotonic)

    def update(self, hand_state: HandState) -> GestureState:
        """Derive gesture state from the tracked hand."""
        raw_cursor = hand_state.index_tip
        if not hand_state.detected or raw_cursor is None:
            self._reset_cursor_filter()
            self.previous_pinch_active = False
            self._pending_pinch_state = False
            self._pinch_state_since = None
            self._active_pinch_finger = None
            return GestureState(tracking_stable=False)

        cursor = self._smooth_cursor(raw_cursor)
        pinch_ratio, raw_finger = self._compute_pinch_info(hand_state)
        raw_pinch = self._compute_raw_pinch_active(pinch_ratio)
        pinch_active = self._debounce_pinch(raw_pinch)
        pinch_started = pinch_active and not self.previous_pinch_active
        pinch_ended = self.previous_pinch_active and not pinch_active

        # Lock the finger identity at pinch start; keep it through the hold.
        if pinch_started:
            self._active_pinch_finger = raw_finger

        # Report the finger on active and ended frames; clear after ended.
        pinch_finger = self._active_pinch_finger if (pinch_active or pinch_ended) else None

        if pinch_ended:
            self._active_pinch_finger = None

        self.previous_pinch_active = pinch_active

        return GestureState(
            cursor_px=cursor,
            raw_cursor_px=raw_cursor,
            pinch_ratio=pinch_ratio,
            pinch_active=pinch_active,
            pinch_started=pinch_started,
            pinch_ended=pinch_ended,
            pinch_finger=pinch_finger,
            clutch_pose=self._compute_clutch_pose(hand_state),
            tracking_stable=True,
        )

    def _smooth_cursor(self, raw_cursor: PixelPoint) -> PixelPoint:
        """Apply the 1€ adaptive filter to the raw cursor position."""
        if self._cursor_filter is None:
            self._cursor_filter = OneEuroFilter(
                min_cutoff=self.config.cursor_filter_min_cutoff,
                beta=self.config.cursor_filter_beta,
                d_cutoff=self.config.cursor_filter_d_cutoff,
                time_fn=self._time_fn,
            )
        return self._cursor_filter.apply(raw_cursor)

    def _reset_cursor_filter(self) -> None:
        """Reset the cursor filter so the next detection starts fresh."""
        if self._cursor_filter is not None:
            self._cursor_filter.reset()

    def _compute_pinch_info(self, hand_state: HandState) -> tuple[float, str]:
        """Compute the pinch ratio and identify which finger is pinching.

        Checks both thumb-index and thumb-middle distances. The finger
        closest to the thumb determines the pinch type:
        - "index" → single click in system mode
        - "middle" → double click in system mode

        Returns (pinch_ratio, finger_name).
        """
        thumb = hand_state.thumb_tip
        index = hand_state.index_tip
        middle = hand_state.landmarks_px.get(_MIDDLE_FINGER_TIP_ID)
        hand_scale = max(hand_state.hand_scale, 1.0)

        index_dist = math.dist(thumb, index) / hand_scale if thumb and index else math.inf
        middle_dist = math.dist(thumb, middle) / hand_scale if thumb and middle else math.inf

        if middle_dist < index_dist:
            return middle_dist, "middle"
        return index_dist, "index"

    def _compute_raw_pinch_active(self, pinch_ratio: float) -> bool:
        """Apply hysteresis thresholds to determine raw pinch state."""
        if self.previous_pinch_active:
            return pinch_ratio <= self.config.pinch_off_threshold
        return pinch_ratio <= self.config.pinch_on_threshold

    def _debounce_pinch(self, raw_pinch: bool) -> bool:
        """Require the raw pinch state to remain stable for a debounce window.

        This prevents rapid on-off-on flicker that hysteresis alone cannot
        catch, especially during quick hand movements near the threshold.
        """
        now = self._time_fn()

        # If the raw signal matches the current committed state, reset debounce.
        if raw_pinch == self.previous_pinch_active:
            self._pending_pinch_state = raw_pinch
            self._pinch_state_since = None
            return self.previous_pinch_active

        # The raw signal disagrees — start or continue the debounce timer.
        if self._pinch_state_since is None or self._pending_pinch_state != raw_pinch:
            self._pinch_state_since = now
            self._pending_pinch_state = raw_pinch

        elapsed_ms = (now - self._pinch_state_since) * 1000.0
        if elapsed_ms >= self.config.pinch_debounce_ms:
            # Debounce window satisfied: commit the new state.
            self._pinch_state_since = None
            return raw_pinch

        # Still within the debounce window: hold the previous state.
        return self.previous_pinch_active

    @staticmethod
    def _compute_clutch_pose(hand_state: HandState) -> bool:
        palm_center = hand_state.palm_center
        if palm_center is None or not hand_state.landmarks_px:
            return False

        extended_fingers = 0
        for mcp_id, tip_id in _CLUTCH_FINGER_PAIRS:
            mcp = hand_state.landmarks_px.get(mcp_id)
            tip = hand_state.landmarks_px.get(tip_id)
            if mcp is None or tip is None:
                continue

            tip_distance = math.dist(tip, palm_center)
            mcp_distance = math.dist(mcp, palm_center)
            if tip_distance >= max(mcp_distance * 1.6, hand_state.hand_scale * 0.75):
                extended_fingers += 1

        return extended_fingers >= 3
