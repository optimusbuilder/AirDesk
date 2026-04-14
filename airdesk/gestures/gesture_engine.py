"""Gesture interpretation from tracked hand landmarks."""

from dataclasses import dataclass
import math

from airdesk.config import GestureConfig
from airdesk.gestures.filters import ema_point
from airdesk.models.gesture import GestureState
from airdesk.models.hand import HandState, PixelPoint


@dataclass(slots=True)
class GestureEngine:
    """Converts hand landmarks into higher-level gesture signals."""

    config: GestureConfig
    previous_cursor: PixelPoint | None = None
    previous_pinch_active: bool = False

    def update(self, hand_state: HandState) -> GestureState:
        """Derive gesture state from the tracked hand."""
        raw_cursor = hand_state.index_tip
        if not hand_state.detected or raw_cursor is None:
            self.previous_cursor = None
            self.previous_pinch_active = False
            return GestureState(tracking_stable=False)

        cursor = ema_point(
            current=raw_cursor,
            previous=self.previous_cursor,
            alpha=self.config.cursor_smoothing_alpha,
        )
        self.previous_cursor = cursor
        pinch_ratio = self._compute_pinch_ratio(hand_state)
        pinch_active = self._compute_pinch_active(pinch_ratio)
        pinch_started = pinch_active and not self.previous_pinch_active
        pinch_ended = self.previous_pinch_active and not pinch_active
        self.previous_pinch_active = pinch_active

        return GestureState(
            cursor_px=cursor,
            raw_cursor_px=raw_cursor,
            pinch_ratio=pinch_ratio,
            pinch_active=pinch_active,
            pinch_started=pinch_started,
            pinch_ended=pinch_ended,
            tracking_stable=True,
        )

    def _compute_pinch_ratio(self, hand_state: HandState) -> float:
        if hand_state.thumb_tip is None or hand_state.index_tip is None:
            return math.inf

        hand_scale = max(hand_state.hand_scale, 1.0)
        return math.dist(hand_state.thumb_tip, hand_state.index_tip) / hand_scale

    def _compute_pinch_active(self, pinch_ratio: float) -> bool:
        if self.previous_pinch_active:
            return pinch_ratio <= self.config.pinch_off_threshold
        return pinch_ratio <= self.config.pinch_on_threshold
