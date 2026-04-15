"""Focused tests for hover, grab, drag, and release behavior."""

from airdesk.config import GestureConfig
from airdesk.core.interaction_controller import InteractionController
from airdesk.core.window_manager import WindowManager
from airdesk.models.gesture import GestureState
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow


def make_manager_with_window() -> WindowManager:
    """Return a window manager seeded with one draggable panel."""
    return WindowManager(
        windows=[VirtualWindow(id="panel", title="Panel", x=100, y=100, width=200, height=140)]
    )


def test_hover_targets_the_frontmost_window() -> None:
    """Overlapping windows should hover the one on top."""
    manager = WindowManager()
    manager.add_window(VirtualWindow(id="back", title="Back", x=100, y=100, width=200, height=140))
    manager.add_window(
        VirtualWindow(id="front", title="Front", x=140, y=130, width=200, height=140)
    )
    controller = InteractionController(config=GestureConfig())
    interaction = InteractionState()

    controller.update(
        GestureState(cursor_px=(180, 170), tracking_stable=True),
        manager,
        interaction,
        640,
        480,
    )

    assert interaction.hovered_window_id == "front"
    assert manager.get_window("front").state.value == "hovered"
    assert manager.get_window("back").state.value == "idle"


def test_pinch_started_over_window_begins_grab_and_drag() -> None:
    """A pinch on a hovered window should capture it and preserve offset."""
    manager = make_manager_with_window()
    controller = InteractionController(config=GestureConfig())
    interaction = InteractionState()

    controller.update(
        GestureState(
            cursor_px=(150, 150),
            raw_cursor_px=(150, 150),
            pinch_started=True,
            pinch_active=True,
            tracking_stable=True,
        ),
        manager,
        interaction,
        640,
        480,
    )
    controller.update(
        GestureState(
            cursor_px=(220, 210),
            raw_cursor_px=(220, 210),
            pinch_active=True,
            tracking_stable=True,
        ),
        manager,
        interaction,
        640,
        480,
    )

    window = manager.get_window("panel")
    assert interaction.grabbed_window_id == "panel"
    assert (interaction.grab_offset_x, interaction.grab_offset_y) == (50, 50)
    assert (window.x, window.y) == (170, 160)
    assert window.state.value == "grabbed"


def test_pinch_end_releases_window_in_place() -> None:
    """Ending the pinch should clear grab state without snapping back."""
    manager = make_manager_with_window()
    controller = InteractionController(config=GestureConfig())
    interaction = InteractionState(grabbed_window_id="panel", grab_offset_x=20, grab_offset_y=30)

    controller.update(
        GestureState(
            cursor_px=(200, 220),
            raw_cursor_px=(200, 220),
            pinch_ended=True,
            tracking_stable=True,
        ),
        manager,
        interaction,
        640,
        480,
    )

    window = manager.get_window("panel")
    assert interaction.grabbed_window_id is None
    assert (window.x, window.y) == (100, 100)
    assert window.state.value == "hovered"


def test_hand_loss_timeout_releases_after_grace_period(monkeypatch) -> None:
    """Temporary tracking loss should only release after the configured timeout."""
    manager = make_manager_with_window()
    controller = InteractionController(config=GestureConfig(hand_loss_timeout_ms=150))
    interaction = InteractionState(grabbed_window_id="panel", grab_offset_x=20, grab_offset_y=20)
    times = iter([100.0, 100.10, 100.30])
    monkeypatch.setattr("airdesk.core.interaction_controller.time.monotonic", lambda: next(times))

    controller.update(
        GestureState(tracking_stable=False),
        manager,
        interaction,
        640,
        480,
    )
    assert interaction.grabbed_window_id == "panel"
    assert interaction.hand_missing_since == 100.0

    controller.update(
        GestureState(tracking_stable=False),
        manager,
        interaction,
        640,
        480,
    )
    assert interaction.grabbed_window_id == "panel"

    controller.update(
        GestureState(tracking_stable=False),
        manager,
        interaction,
        640,
        480,
    )
    assert interaction.grabbed_window_id is None
    assert interaction.hand_missing_since is None
