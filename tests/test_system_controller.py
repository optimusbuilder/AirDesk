"""Tests for the new system-intent architecture."""

from argparse import Namespace

from airdesk.config import AppMode
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
        SystemIntentController(enabled=True).update(
            GestureState(cursor_px=(320, 240), tracking_stable=True),
            640,
            480,
        )
    )

    assert state.backend_name == "macos"
    assert "Live macOS move" in state.effect_label
    assert backend.bridge.calls == [("move", (721, 450))]


def test_macos_backend_requires_accessibility_permission() -> None:
    """Live backend should refuse to act until Accessibility trust is granted."""
    bridge = FakeMacOSBridge(trusted=False)
    backend = MacOSSystemBackend(bridge=bridge)

    state = backend.apply(
        SystemIntentController(enabled=True).update(
            GestureState(cursor_px=(320, 240), tracking_stable=True),
            640,
            480,
        )
    )

    assert bridge.calls == []
    assert "Accessibility" in state.effect_label


def test_macos_backend_reset_releases_any_held_button() -> None:
    """Disarming live control should release the primary button safely."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    controller = SystemIntentController(enabled=True)

    backend.apply(
        controller.update(
            GestureState(
                cursor_px=(320, 240),
                tracking_stable=True,
                pinch_started=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    backend.reset()

    assert bridge.calls == [("down", (721, 450)), ("up", (721, 450))]
