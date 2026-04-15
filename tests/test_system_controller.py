"""Tests for the new system-intent architecture."""

from airdesk.models.gesture import GestureState
from airdesk.platform.shadow import ShadowSystemBackend
from airdesk.system.controller import SystemIntentController
from airdesk.system.intents import PointerPhase


def test_disabled_system_controller_returns_disabled_state() -> None:
    """Disabled mode should not emit active system-control intents."""
    controller = SystemIntentController(enabled=False)

    state = controller.update(
        GestureState(cursor_px=(120, 80), tracking_stable=True),
        640,
        480,
    )

    assert state.enabled is False
    assert state.phase is PointerPhase.IDLE
    assert state.backend_name == "disabled"


def test_system_controller_emits_move_press_drag_release_flow() -> None:
    """Gesture transitions should map cleanly to pointer-style intents."""
    controller = SystemIntentController(enabled=True)

    move = controller.update(GestureState(cursor_px=(100, 120), tracking_stable=True), 640, 480)
    press = controller.update(
        GestureState(
            cursor_px=(100, 120),
            tracking_stable=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )
    drag = controller.update(
        GestureState(cursor_px=(140, 180), tracking_stable=True, pinch_active=True),
        640,
        480,
    )
    release = controller.update(
        GestureState(cursor_px=(140, 180), tracking_stable=True, pinch_ended=True),
        640,
        480,
    )

    assert move.phase is PointerPhase.MOVE
    assert move.normalized_cursor is not None
    assert move.button_down is False
    assert press.phase is PointerPhase.PRESS
    assert press.button_down is True
    assert drag.phase is PointerPhase.DRAG
    assert drag.button_down is True
    assert release.phase is PointerPhase.RELEASE
    assert release.button_down is False


def test_tracking_loss_forces_release_when_button_was_down() -> None:
    """Losing the hand while dragging should produce a safe forced release."""
    controller = SystemIntentController(enabled=True)
    controller.update(
        GestureState(
            cursor_px=(200, 200),
            tracking_stable=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )

    lost = controller.update(GestureState(tracking_stable=False), 640, 480)

    assert lost.phase is PointerPhase.RELEASE
    assert lost.button_down is False
    assert "force" in lost.effect_label.lower()


def test_shadow_backend_labels_actions_human_readably() -> None:
    """Shadow backend should annotate emitted system intents for the UI."""
    controller = SystemIntentController(enabled=True)
    backend = ShadowSystemBackend()

    state = controller.update(
        GestureState(cursor_px=(250, 160), tracking_stable=True),
        640,
        480,
    )
    state = backend.apply(state)

    assert state.backend_name == "shadow"
    assert state.phase is PointerPhase.MOVE
    assert "Shadow move" in state.effect_label
