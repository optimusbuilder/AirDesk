"""Tests for the new system-intent architecture."""

from argparse import Namespace

from airdesk.config import AppMode, SystemControlConfig
from airdesk.main import build_arg_parser, build_config_from_args, validate_args
from airdesk.models.gesture import GestureState
from airdesk.platform.macos import MacOSSystemBackend
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
    """Gesture transitions should map cleanly once the clutch is engaged."""
    times = iter([100.0, 100.25, 100.31, 100.40, 100.50, 100.60, 100.70])
    controller = SystemIntentController(
        config=SystemControlConfig(clutch_activation_ms=180, pinch_press_delay_ms=60),
        enabled=True,
        time_fn=lambda: next(times),
    )

    waiting = controller.update(
        GestureState(cursor_px=(100, 120), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    move = controller.update(
        GestureState(cursor_px=(100, 120), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    debounce = controller.update(
        GestureState(
            cursor_px=(100, 120),
            tracking_stable=True,
            clutch_pose=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )
    press = controller.update(
        GestureState(
            cursor_px=(100, 120),
            tracking_stable=True,
            clutch_pose=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )
    drag = controller.update(
        GestureState(cursor_px=(140, 180), tracking_stable=True, clutch_pose=True, pinch_active=True),
        640,
        480,
    )
    release = controller.update(
        GestureState(cursor_px=(140, 180), tracking_stable=True, clutch_pose=True, pinch_ended=True),
        640,
        480,
    )

    assert waiting.phase is PointerPhase.IDLE
    assert move.phase is PointerPhase.MOVE
    assert move.normalized_cursor is not None
    assert move.button_down is False
    assert debounce.phase is PointerPhase.MOVE
    assert "Hold the pinch briefly" in debounce.effect_label
    assert press.phase is PointerPhase.PRESS
    assert press.button_down is True
    assert drag.phase is PointerPhase.DRAG
    assert drag.button_down is True
    assert release.phase is PointerPhase.RELEASE
    assert release.button_down is False


def test_tracking_loss_forces_release_when_button_was_down() -> None:
    """Losing the hand while dragging should produce a safe forced release."""
    times = iter([100.0, 100.25, 100.40, 100.50])
    controller = SystemIntentController(
        config=SystemControlConfig(clutch_activation_ms=180, pinch_press_delay_ms=60),
        enabled=True,
        time_fn=lambda: next(times),
    )
    controller.update(
        GestureState(cursor_px=(200, 200), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    controller.update(
        GestureState(
            cursor_px=(200, 200),
            tracking_stable=True,
            clutch_pose=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )
    controller.update(
        GestureState(
            cursor_px=(200, 200),
            tracking_stable=True,
            clutch_pose=True,
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
    times = iter([100.0, 100.25])
    controller = SystemIntentController(enabled=True, time_fn=lambda: next(times))
    backend = ShadowSystemBackend()

    controller.update(
        GestureState(cursor_px=(250, 160), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )

    state = controller.update(
        GestureState(cursor_px=(250, 160), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    state = backend.apply(state)

    assert state.backend_name == "shadow"
    assert state.phase is PointerPhase.MOVE
    assert "Shadow move" in state.effect_label


def test_system_controller_requires_clutch_pose_before_moving() -> None:
    """System control should wait for an open-palm clutch before steering."""
    controller = SystemIntentController(enabled=True, time_fn=lambda: 100.0)

    state = controller.update(
        GestureState(cursor_px=(180, 120), tracking_stable=True, clutch_pose=False),
        640,
        480,
    )

    assert state.phase is PointerPhase.IDLE
    assert state.clutch_engaged is False
    assert "open palm" in state.effect_label.lower()


def test_system_controller_deadzone_reuses_previous_output_cursor() -> None:
    """Tiny cursor shifts should be filtered by the controller deadzone."""
    times = iter([100.0, 100.25, 100.30])
    controller = SystemIntentController(
        config=SystemControlConfig(
            clutch_activation_ms=180,
            pinch_press_delay_ms=60,
            cursor_deadzone_px=12,
        ),
        enabled=True,
        time_fn=lambda: next(times),
    )

    controller.update(
        GestureState(cursor_px=(200, 200), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    first_move = controller.update(
        GestureState(cursor_px=(200, 200), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    second_move = controller.update(
        GestureState(cursor_px=(204, 202), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )

    assert first_move.normalized_cursor == second_move.normalized_cursor


def test_live_system_flags_are_applied_to_config() -> None:
    """CLI flags should flow into the live-system config cleanly."""
    args = Namespace(
        mode=AppMode.SYSTEM_MACOS.value,
        camera_index=None,
        enable_system_actions=True,
        start_armed=True,
        show_debug_hud=False,
        hide_debug_hud=False,
    )

    config = build_config_from_args(args)

    assert config.system.mode is AppMode.SYSTEM_MACOS
    assert config.system.enable_live_backend is True
    assert config.system.start_armed is True


def test_live_system_cli_rejects_invalid_safety_combinations() -> None:
    """Safety toggles should only work with the live macOS backend."""
    parser = build_arg_parser()

    args = parser.parse_args(["--mode", AppMode.SYSTEM_SHADOW.value, "--enable-system-actions"])

    try:
        validate_args(args, parser)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected CLI validation to reject live-system flags in shadow mode")


class FakeMacOSBridge:
    """Tiny fake CoreGraphics bridge for backend unit tests."""

    def __init__(
        self,
        *,
        trusted: bool = True,
        bounds: tuple[float, float, float, float] = (0.0, 0.0, 1440.0, 900.0),
    ) -> None:
        self._trusted = trusted
        self._bounds = bounds
        self.calls: list[tuple[str, tuple[float, float]]] = []

    def accessibility_is_trusted(self) -> bool:
        return self._trusted

    def main_display_bounds(self) -> tuple[float, float, float, float]:
        return self._bounds

    def move_cursor(self, point: tuple[float, float]) -> None:
        self.calls.append(("move", point))

    def post_primary_down(self, point: tuple[float, float]) -> None:
        self.calls.append(("down", point))

    def post_primary_drag(self, point: tuple[float, float]) -> None:
        self.calls.append(("drag", point))

    def post_primary_up(self, point: tuple[float, float]) -> None:
        self.calls.append(("up", point))


def test_macos_backend_maps_normalized_cursor_to_main_display() -> None:
    """Live backend should translate normalized points into screen coordinates."""
    backend = MacOSSystemBackend(bridge=FakeMacOSBridge())

    state = backend.apply(
        SystemIntentController(
            enabled=True,
            time_fn=lambda: 100.0,
        ).update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=False),
            640,
            480,
        )
    )

    assert state.backend_name == "macos"
    assert "open palm" in state.effect_label.lower()
    assert backend.bridge.calls == []


def test_macos_backend_moves_after_clutch_is_engaged() -> None:
    """Live backend should move the real pointer only after the clutch engages."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    times = iter([100.0, 100.25])
    controller = SystemIntentController(enabled=True, time_fn=lambda: next(times))

    controller.update(
        GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    state = backend.apply(
        controller.update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
            640,
            480,
        )
    )

    assert state.backend_name == "macos"
    assert "Live macOS move" in state.effect_label
    assert bridge.calls == [("move", (721, 451))]


def test_macos_backend_requires_accessibility_permission() -> None:
    """Live backend should refuse to act until Accessibility trust is granted."""
    bridge = FakeMacOSBridge(trusted=False)
    backend = MacOSSystemBackend(bridge=bridge)

    state = backend.apply(
        SystemIntentController(enabled=True, time_fn=lambda: 100.0).update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=False),
            640,
            480,
        )
    )

    assert bridge.calls == []
    assert "Accessibility" in state.effect_label
    assert state.permission_granted is False


def test_macos_backend_reset_releases_any_held_button() -> None:
    """Disarming live control should release the primary button safely."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    times = iter([100.0, 100.25, 100.35, 100.45])
    controller = SystemIntentController(
        config=SystemControlConfig(clutch_activation_ms=180, pinch_press_delay_ms=60),
        enabled=True,
        time_fn=lambda: next(times),
    )

    controller.update(
        GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )

    backend.apply(
        controller.update(
            GestureState(
                cursor_px=(320, 240),
                tracking_stable=True,
                clutch_pose=True,
                pinch_started=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    backend.apply(
        controller.update(
            GestureState(
                cursor_px=(320, 240),
                tracking_stable=True,
                clutch_pose=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    backend.reset()

    assert bridge.calls == [("move", (721, 451)), ("down", (721, 451)), ("up", (721, 451))]
