"""Tests for the system controller."""

import pytest

from airdesk.config import SystemControlConfig
from airdesk.models.gesture import GestureState
from airdesk.system.controller import SystemIntentController
from airdesk.system.intents import PointerPhase


def test_controller_requires_finger_in_trackpad() -> None:
    """The controller should remain IDLE until the finger enters the trackpad bounds."""
    # Frame is 640x480. Trackpad is 340x200, bottom offset 20.
    # Trackpad X: (640 - 340) / 2 = 150 to 490
    # Trackpad Y: 480 - 20 - 200 = 260 to 460
    config = SystemControlConfig(trackpad_width=340, trackpad_height=200, trackpad_bottom_offset=20)
    controller = SystemIntentController(config=config, enabled=True)

    # Outside trackpad
    state = controller.update(
        GestureState(cursor_px=(100, 100), tracking_stable=True),
        640,
        480,
    )
    assert state.phase is PointerPhase.IDLE
    assert not state.clutch_engaged

    # Inside trackpad
    state = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True),
        640,
        480,
    )
    assert state.phase is PointerPhase.MOVE
    assert state.clutch_engaged


def test_controller_maps_trackpad_to_normalized_screen() -> None:
    """The controller should map the physical trackpad bounds to 0.0-1.0 normalized coordinates."""
    config = SystemControlConfig(trackpad_width=340, trackpad_height=200, trackpad_bottom_offset=20, cursor_deadzone_px=0)
    controller = SystemIntentController(config=config, enabled=True)

    # Top-left of trackpad (150, 260)
    state = controller.update(
        GestureState(cursor_px=(150, 260), tracking_stable=True),
        640,
        480,
    )
    assert state.normalized_cursor == (0.0, 0.0)

    # Bottom-right of trackpad (490, 460)
    state = controller.update(
        GestureState(cursor_px=(490, 460), tracking_stable=True),
        640,
        480,
    )
    assert state.normalized_cursor == (1.0, 1.0)

    # Center of trackpad (320, 360)
    state = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True),
        640,
        480,
    )
    assert state.normalized_cursor == (0.5, 0.5)


def test_exiting_trackpad_drops_clutch_and_forces_release() -> None:
    """Leaving the trackpad bounds should force a button release if dragging."""
    config = SystemControlConfig()
    times = iter([100.0, 100.3, 100.4, 100.5])
    controller = SystemIntentController(config=config, enabled=True, time_fn=lambda: next(times))

    # Enter trackpad and pinch
    controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True, pinch_active=True),
        640,
        480,
    )
    # Pinch for 300ms to trigger PRESS
    drag_state = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True, pinch_active=True),
        640,
        480,
    )
    assert drag_state.phase is PointerPhase.PRESS
    
    # Next frame is DRAG
    drag_state = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True, pinch_active=True),
        640,
        480,
    )
    assert drag_state.phase is PointerPhase.DRAG

    # Exit trackpad
    exit_state = controller.update(
        GestureState(cursor_px=(10, 10), tracking_stable=True, pinch_active=True),
        640,
        480,
    )
    assert exit_state.phase is PointerPhase.RELEASE
    assert not exit_state.clutch_engaged


def test_dwell_click_fires_after_holding_still() -> None:
    """Holding the cursor still inside the trackpad should fire a click."""
    config = SystemControlConfig(dwell_single_ms=800, dwell_double_ms=1800, cursor_deadzone_px=0)
    times = iter([0.0, 0.81, 1.81])
    controller = SystemIntentController(config=config, enabled=True, time_fn=lambda: next(times))

    # Move to center
    state1 = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True),
        640,
        480,
    )
    assert state1.phase is PointerPhase.MOVE

    # Hold still for 810ms
    state2 = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True),
        640,
        480,
    )
    assert state2.phase is PointerPhase.CLICK
    assert state2.click_count == 1

    # Hold still for 1810ms
    state3 = controller.update(
        GestureState(cursor_px=(320, 360), tracking_stable=True),
        640,
        480,
    )
    assert state3.phase is PointerPhase.CLICK
    assert state3.click_count == 2
