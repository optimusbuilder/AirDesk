"""Focused tests for gesture smoothing and pinch behavior."""

import math
import time

from airdesk.config import GestureConfig
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.hand import HandState


def _make_frozen_time():
    """Return a monotonic time function and an advance helper for tests."""
    current = [0.0]

    def time_fn():
        return current[0]

    def advance(seconds: float):
        current[0] += seconds

    return time_fn, advance


def make_hand_state(
    *,
    index_tip=(100, 100),
    thumb_tip=(140, 100),
    hand_scale=100.0,
    detected=True,
    palm_center=None,
    landmarks_px=None,
):
    """Return a minimal hand state for gesture tests."""
    return HandState(
        detected=detected,
        index_tip=index_tip,
        thumb_tip=thumb_tip,
        palm_center=palm_center,
        landmarks_px=landmarks_px or {},
        hand_scale=hand_scale,
    )


def _make_engine(**kwargs):
    """Create a GestureEngine with frozen time and optional config overrides."""
    time_fn, advance = _make_frozen_time()
    config = GestureConfig(**kwargs)
    engine = GestureEngine(config=config, _time_fn=time_fn)
    return engine, advance


def test_cursor_follows_index_fingertip() -> None:
    """The cursor should track the index finger position."""
    engine, advance = _make_engine()

    advance(0.033)
    first = engine.update(make_hand_state(index_tip=(100, 100)))
    assert first.cursor_px == (100, 100)
    assert first.tracking_stable is True


def test_cursor_resets_after_tracking_loss() -> None:
    """After hand loss and reacquisition, cursor should start fresh."""
    engine, advance = _make_engine()

    advance(0.033)
    engine.update(make_hand_state(index_tip=(100, 100)))
    advance(0.033)
    engine.update(make_hand_state(index_tip=(200, 200)))

    advance(0.033)
    lost = engine.update(HandState())
    assert lost.tracking_stable is False
    assert lost.cursor_px is None

    # After loss, the first frame should snap to the new position.
    advance(0.033)
    reacquired = engine.update(make_hand_state(index_tip=(160, 160)))
    assert reacquired.cursor_px == (160, 160)


def test_cursor_smoothing_reduces_jitter() -> None:
    """The 1€ filter should smooth small movements when the hand is still."""
    engine, advance = _make_engine()

    advance(0.033)
    engine.update(make_hand_state(index_tip=(200, 200)))

    # Small jitter around the same position should be dampened.
    advance(0.033)
    s1 = engine.update(make_hand_state(index_tip=(202, 198)))
    advance(0.033)
    s2 = engine.update(make_hand_state(index_tip=(199, 201)))

    # The smoothed cursor shouldn't jump by the full jitter amount.
    assert abs(s1.cursor_px[0] - 200) < 5
    assert abs(s2.cursor_px[0] - 200) < 5


def test_pinch_hysteresis_emits_stable_started_hold_and_end() -> None:
    """Pinch state should honor separate on/off thresholds."""
    engine, advance = _make_engine(
        pinch_on_threshold=0.30,
        pinch_off_threshold=0.40,
        pinch_debounce_ms=0,  # Disable debounce for hysteresis-only test
    )

    advance(0.033)
    idle = engine.update(make_hand_state(thumb_tip=(150, 100)))
    advance(0.033)
    started = engine.update(make_hand_state(thumb_tip=(125, 100)))
    advance(0.033)
    held = engine.update(make_hand_state(thumb_tip=(135, 100)))
    advance(0.033)
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
    engine, advance = _make_engine()

    advance(0.033)
    state = engine.update(make_hand_state(thumb_tip=None))

    assert state.tracking_stable is True
    assert state.pinch_active is False
    assert math.isinf(state.pinch_ratio)


def test_pinch_debounce_prevents_rapid_flicker() -> None:
    """Brief threshold crossings should be absorbed by the debounce timer."""
    engine, advance = _make_engine(
        pinch_on_threshold=0.30,
        pinch_off_threshold=0.40,
        pinch_debounce_ms=40,
    )

    # Start pinching (below on threshold).
    advance(0.033)
    engine.update(make_hand_state(thumb_tip=(125, 100)))

    # The debounce hasn't been satisfied yet at this frame time.
    advance(0.020)
    still_off = engine.update(make_hand_state(thumb_tip=(125, 100)))

    # At 20ms, should still be in previous state (off) since debounce is 40ms.
    assert still_off.pinch_active is False

    # After enough time, the debounce should commit the pinch.
    advance(0.030)
    now_on = engine.update(make_hand_state(thumb_tip=(125, 100)))
    assert now_on.pinch_active is True
    assert now_on.pinch_started is True


def test_pinch_debounce_absorbs_brief_release() -> None:
    """A momentary unclench during a held pinch should not release."""
    engine, advance = _make_engine(
        pinch_on_threshold=0.30,
        pinch_off_threshold=0.40,
        pinch_debounce_ms=40,
    )

    # Establish a stable pinch.
    advance(0.033)
    engine.update(make_hand_state(thumb_tip=(125, 100)))
    advance(0.050)
    engine.update(make_hand_state(thumb_tip=(125, 100)))
    assert engine.previous_pinch_active is True

    # Brief release (above off threshold) for less than debounce window.
    advance(0.020)
    brief = engine.update(make_hand_state(thumb_tip=(148, 100)))
    assert brief.pinch_active is True  # Still held due to debounce.

    # Return to pinching before debounce expires.
    advance(0.010)
    back = engine.update(make_hand_state(thumb_tip=(125, 100)))
    assert back.pinch_active is True  # Never released.


def test_open_palm_sets_clutch_pose_true() -> None:
    """An open hand should advertise the clutch pose to system control."""
    engine, advance = _make_engine()
    landmarks = {
        5: (76, 120),
        8: (76, 36),
        9: (96, 120),
        12: (96, 30),
        13: (116, 120),
        16: (116, 34),
        17: (136, 120),
        20: (136, 42),
    }

    advance(0.033)
    state = engine.update(
        make_hand_state(
            index_tip=(76, 36),
            thumb_tip=(52, 88),
            palm_center=(106, 100),
            landmarks_px=landmarks,
            hand_scale=60.0,
        )
    )

    assert state.clutch_pose is True


def test_curled_fingers_keep_clutch_pose_false() -> None:
    """A non-open hand should not engage the system clutch pose."""
    engine, advance = _make_engine()
    landmarks = {
        5: (76, 120),
        8: (84, 96),
        9: (96, 120),
        12: (102, 100),
        13: (116, 120),
        16: (118, 102),
        17: (136, 120),
        20: (130, 104),
    }

    advance(0.033)
    state = engine.update(
        make_hand_state(
            index_tip=(84, 96),
            thumb_tip=(70, 96),
            palm_center=(106, 100),
            landmarks_px=landmarks,
            hand_scale=60.0,
        )
    )

    assert state.clutch_pose is False
