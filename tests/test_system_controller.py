"""Tests for the new system-intent architecture."""

from argparse import Namespace

from airdesk.config import AppMode, SystemControlConfig
from airdesk.main import build_arg_parser, build_config_from_args, validate_args
from airdesk.models.gesture import GestureState
from airdesk.platform.macos import MacOSSystemBackend
from airdesk.platform.shadow import ShadowSystemBackend
from airdesk.system.controller import SystemIntentController
from airdesk.system.intents import ControlMode, PointerPhase, WindowActionMode


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
    assert "Tap to click, hold the pinch to drag" in debounce.effect_label
    assert press.phase is PointerPhase.PRESS
    assert press.button_down is True
    assert drag.phase is PointerPhase.DRAG
    assert drag.button_down is True
    assert release.phase is PointerPhase.RELEASE
    assert release.button_down is False


def test_system_controller_emits_click_for_a_quick_pinch_tap() -> None:
    """A short thumb-index tap should become a click instead of a drag."""
    times = iter([100.0, 100.25, 100.28, 100.31])
    controller = SystemIntentController(
        config=SystemControlConfig(clutch_activation_ms=180, pinch_press_delay_ms=60),
        enabled=True,
        time_fn=lambda: next(times),
    )

    controller.update(
        GestureState(cursor_px=(180, 140), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    controller.update(
        GestureState(cursor_px=(180, 140), tracking_stable=True, clutch_pose=True),
        640,
        480,
    )
    controller.update(
        GestureState(
            cursor_px=(180, 140),
            tracking_stable=True,
            clutch_pose=True,
            pinch_started=True,
            pinch_active=True,
        ),
        640,
        480,
    )
    click = controller.update(
        GestureState(
            cursor_px=(182, 141),
            tracking_stable=True,
            clutch_pose=True,
            pinch_ended=True,
        ),
        640,
        480,
    )

    assert click.phase is PointerPhase.CLICK
    assert click.button_down is False
    assert "click" in click.effect_label.lower()


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
        focused_window_title: str | None = "Notes",
        focused_window_bounds: tuple[float, float, float, float] | None = (120.0, 160.0, 900.0, 700.0),
        focused_window_pid: int = 4242,
        window_position_settable: bool = True,
        window_size_settable: bool = True,
    ) -> None:
        self._trusted = trusted
        self._bounds = bounds
        self._windows: dict[object, dict[str, object]] = {}
        self._focused_window_ref: object | None = None
        if focused_window_bounds is not None:
            self._focused_window_ref = self.add_window(
                title=focused_window_title,
                bounds=focused_window_bounds,
                pid=focused_window_pid,
                position_settable=window_position_settable,
                size_settable=window_size_settable,
            )
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

    def copy_focused_window(self) -> object | None:
        return self._focused_window_ref

    def release_ref(self, ref: object | None) -> None:
        return None

    def copy_window_title(self, window_ref: object) -> str | None:
        data = self._windows.get(window_ref)
        if data is None:
            return None
        return data["title"] if isinstance(data["title"], str) else None

    def copy_window_bounds(self, window_ref: object) -> tuple[float, float, float, float] | None:
        data = self._windows.get(window_ref)
        if data is None:
            return None
        return data["bounds"] if isinstance(data["bounds"], tuple) else None

    def is_window_position_settable(self, window_ref: object) -> bool:
        data = self._windows.get(window_ref)
        return bool(data["position_settable"]) if data is not None else False

    def is_window_size_settable(self, window_ref: object) -> bool:
        data = self._windows.get(window_ref)
        return bool(data["size_settable"]) if data is not None else False

    def window_pid(self, window_ref: object) -> int | None:
        data = self._windows.get(window_ref)
        return int(data["pid"]) if data is not None else None

    def move_window_to(self, window_ref: object, origin: tuple[float, float]) -> None:
        data = self._windows.get(window_ref)
        if data is not None:
            _, _, width, height = data["bounds"]
            data["bounds"] = (origin[0], origin[1], width, height)
        self.calls.append(("window-move", origin))

    def resize_window_to(self, window_ref: object, size: tuple[float, float]) -> None:
        data = self._windows.get(window_ref)
        if data is not None:
            origin_x, origin_y, _, _ = data["bounds"]
            data["bounds"] = (origin_x, origin_y, size[0], size[1])
        self.calls.append(("window-resize", size))

    def add_window(
        self,
        *,
        title: str | None,
        bounds: tuple[float, float, float, float],
        pid: int,
        position_settable: bool,
        size_settable: bool,
    ) -> object:
        window_ref = object()
        self._windows[window_ref] = {
            "title": title,
            "bounds": bounds,
            "pid": pid,
            "position_settable": position_settable,
            "size_settable": size_settable,
        }
        return window_ref

    def set_focused_window(
        self,
        *,
        title: str | None,
        bounds: tuple[float, float, float, float] | None,
        pid: int,
        position_settable: bool = True,
        size_settable: bool = True,
    ) -> None:
        if bounds is None:
            self._focused_window_ref = None
            return
        self._focused_window_ref = self.add_window(
            title=title,
            bounds=bounds,
            pid=pid,
            position_settable=position_settable,
            size_settable=size_settable,
        )


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


def test_macos_backend_turns_a_quick_tap_into_a_click() -> None:
    """A short pinch tap should post a primary down/up pair in pointer mode."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    times = iter([100.0, 100.25, 100.28, 100.31])
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
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
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
                pinch_started=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    clicked = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(321, 241),
                tracking_stable=True,
                clutch_pose=True,
                pinch_ended=True,
            ),
            640,
            480,
        )
    )

    assert clicked.phase is PointerPhase.CLICK
    assert clicked.effect_label == "Live macOS click at 721, 451"
    assert bridge.calls == [
        ("move", (721, 451)),
        ("move", (721, 451)),
        ("down", (721, 451)),
        ("up", (721, 451)),
    ]


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


def test_macos_backend_window_mode_moves_the_focused_window() -> None:
    """Window mode should move the focused external window instead of the pointer."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    backend.set_control_mode(ControlMode.WINDOW)
    times = iter([100.0, 100.25, 100.35, 100.45, 100.55, 100.65])
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
    ready = backend.apply(
        controller.update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
            640,
            480,
        )
    )
    grabbed = backend.apply(
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
    grabbed = backend.apply(
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
    moved = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(380, 300),
                tracking_stable=True,
                clutch_pose=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    released = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(380, 300),
                tracking_stable=True,
                clutch_pose=True,
                pinch_ended=True,
            ),
            640,
            480,
        )
    )

    assert ready.control_mode is ControlMode.WINDOW
    assert ready.target_label == "Notes"
    assert grabbed.target_locked is True
    assert grabbed.effect_label == 'Grabbed "Notes" for movement'
    assert moved.effect_label == 'Moving "Notes" to 310, 318'
    assert released.effect_label == 'Released "Notes"'
    assert bridge.calls == [("window-move", (310, 318))]


def test_macos_backend_window_mode_resizes_the_locked_window() -> None:
    """Window mode should resize the locked target when resize action is active."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    backend.set_control_mode(ControlMode.WINDOW)

    action_message = backend.toggle_window_action_mode()

    assert action_message == "Window action switched to resize."
    assert backend.window_action_mode is WindowActionMode.RESIZE

    times = iter([100.0, 100.25, 100.35, 100.45, 100.55, 100.65])
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
    ready = backend.apply(
        controller.update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
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
                pinch_started=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    grabbed = backend.apply(
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
    resized = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(380, 300),
                tracking_stable=True,
                clutch_pose=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    released = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(380, 300),
                tracking_stable=True,
                clutch_pose=True,
                pinch_ended=True,
            ),
            640,
            480,
        )
    )

    assert ready.window_action_mode is WindowActionMode.RESIZE
    assert 'ready to resize "notes"' in ready.effect_label.lower()
    assert grabbed.effect_label == 'Grabbed top-right corner of "Notes" for resize'
    assert resized.effect_label == 'Resizing "Notes" to 1090 x 542'
    assert released.effect_label == 'Released resize on "Notes"'
    assert bridge.calls == [
        ("window-move", (120, 318)),
        ("window-resize", (1090, 542)),
    ]
    assert bridge.copy_window_bounds(backend._locked_window_ref) == (120, 318, 1090, 542)


def test_macos_backend_window_mode_snaps_left_on_release_near_edge() -> None:
    """Window move mode should snap the target when released near a screen edge."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    backend.set_control_mode(ControlMode.WINDOW)
    times = iter([100.0, 100.25, 100.35, 100.45, 100.55, 100.65])
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
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
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
    preview = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(0, 200),
                tracking_stable=True,
                clutch_pose=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )
    released = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(0, 200),
                tracking_stable=True,
                clutch_pose=True,
                pinch_ended=True,
            ),
            640,
            480,
        )
    )

    assert preview.effect_label == 'Release to snap "Notes" left'
    assert released.effect_label == 'Snapped "Notes" left'
    assert bridge.calls[-2:] == [
        ("window-move", (0, 0)),
        ("window-resize", (720, 900)),
    ]
    assert bridge.copy_window_bounds(backend._locked_window_ref) == (0, 0, 720, 900)


def test_macos_backend_locked_window_survives_focus_returning_to_airdesk() -> None:
    """Once locked, the backend should keep moving the same window after focus changes."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    backend.set_control_mode(ControlMode.WINDOW)
    backend._process_pid = 0

    lock_message = backend.toggle_target_lock()

    assert lock_message == 'Locked "Notes" as the window target.'

    bridge.set_focused_window(
        title="AirDesk",
        bounds=(20.0, 20.0, 640.0, 480.0),
        pid=0,
    )
    times = iter([100.0, 100.25, 100.35, 100.45, 100.55, 100.65])
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
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=True),
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
    moved = backend.apply(
        controller.update(
            GestureState(
                cursor_px=(360, 260),
                tracking_stable=True,
                clutch_pose=True,
                pinch_active=True,
            ),
            640,
            480,
        )
    )

    assert moved.target_locked is True
    assert moved.target_label == "Notes"
    assert moved.effect_label == 'Moving "Notes" to 247, 213'
    assert bridge.calls == [("window-move", (247, 213))]


def test_macos_backend_toggle_target_lock_clears_existing_target() -> None:
    """The target-lock hotkey should also clear an existing locked window."""
    bridge = FakeMacOSBridge()
    backend = MacOSSystemBackend(bridge=bridge)
    backend.set_control_mode(ControlMode.WINDOW)

    first = backend.toggle_target_lock()
    second = backend.toggle_target_lock()

    assert first == 'Locked "Notes" as the window target.'
    assert second == 'Cleared locked window target "Notes".'


def test_macos_backend_window_mode_ignores_its_own_process_window() -> None:
    """Window mode should refuse to move the AirDesk/OpenCV window itself."""
    bridge = FakeMacOSBridge(focused_window_pid=0)
    backend = MacOSSystemBackend(bridge=bridge)
    backend._process_pid = 0
    backend.set_control_mode(ControlMode.WINDOW)

    state = backend.apply(
        SystemIntentController(enabled=True, time_fn=lambda: 100.0).update(
            GestureState(cursor_px=(320, 240), tracking_stable=True, clutch_pose=False),
            640,
            480,
        )
    )

    assert state.target_label is None
    assert "focus another app window" in state.effect_label.lower()
