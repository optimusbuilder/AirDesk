"""Focused tests for gesture smoothing and pinch behavior."""

import math

from airdesk.config import GestureConfig
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.hand import HandState


def make_hand_state(
    *,
    index_tip=(100, 100),
    thumb_tip=(140, 100),
    hand_scale=100.0,
    detected=True,
):
    """Return a minimal hand state for gesture tests."""
    return HandState(
        detected=detected,
        index_tip=index_tip,
        thumb_tip=thumb_tip,
        hand_scale=hand_scale,
    )


def test_cursor_smoothing_resets_after_tracking_loss() -> None:
    """The cursor should smooth across frames, then reset after loss."""
    engine = GestureEngine(config=GestureConfig(cursor_smoothing_alpha=0.40))

    first = engine.update(make_hand_state(index_tip=(100, 100)))
    second = engine.update(make_hand_state(index_tip=(200, 200)))
    lost = engine.update(HandState())
    reacquired = engine.update(make_hand_state(index_tip=(160, 160)))

    assert first.cursor_px == (100, 100)
    assert second.cursor_px == (140, 140)
    assert lost.tracking_stable is False
    assert lost.cursor_px is None
    assert reacquired.cursor_px == (160, 160)


def test_pinch_hysteresis_emits_stable_started_hold_and_end() -> None:
    """Pinch state should honor separate on/off thresholds."""
    engine = GestureEngine(
        config=GestureConfig(
            pinch_on_threshold=0.30,
            pinch_off_threshold=0.40,
        )
    )

    idle = engine.update(make_hand_state(thumb_tip=(150, 100)))
    started = engine.update(make_hand_state(thumb_tip=(125, 100)))
    held = engine.update(make_hand_state(thumb_tip=(135, 100)))
    ended = engine.update(make_hand_state(thumb_tip=(145, 100)))

    assert idle.pinch_active is False
    assert started.pinch_started is True
    assert started.pinch_active is True
    assert math.isclose(started.pinch_ratio, 0.25)
    assert held.pinch_active is True
    assert held.pinch_started is False
    assert ended.pinch_ended is True
    assert ended.pinch_active is False


def test_missing_thumb_tip_disables_pinch_detection() -> None:
    """Pinch should degrade safely when landmarks are incomplete."""
    engine = GestureEngine(config=GestureConfig())

    state = engine.update(make_hand_state(thumb_tip=None))

    assert state.tracking_stable is True
    assert state.pinch_active is False
    assert math.isinf(state.pinch_ratio)
