"""Application shell for the AirDesk prototype."""

from dataclasses import dataclass, field

from airdesk.config import AppConfig, AppMode, build_default_config
from airdesk.core.interaction_controller import InteractionController
from airdesk.core.window_manager import WindowManager
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow, WindowState
from airdesk.platform.base import SystemBackend
from airdesk.platform.macos import MacOSSystemBackend
from airdesk.platform.shadow import ShadowSystemBackend
from airdesk.system.controller import SystemIntentController
from airdesk.system.intents import (
    ControlMode,
    PointerPhase,
    SystemControlState,
    WindowActionMode,
)
from airdesk.ui.renderer import Renderer
from airdesk.vision.camera import CameraStream
from airdesk.vision.hand_tracker import HandTracker


@dataclass(slots=True)
class AirDeskApp:
    """Top-level application wrapper for future runtime orchestration."""

    config: AppConfig = field(default_factory=build_default_config)
    window_title: str = "AirDesk"

    def run(self) -> int:
        """Start the application runtime."""
        try:
            import cv2
        except ModuleNotFoundError:
            print("AirDesk could not start: OpenCV is not installed. Run `pip install -e .` first.")
            return 1

        camera_stream = CameraStream(self.config.camera)
        hand_tracker: HandTracker | None = None
        gesture_engine = GestureEngine(config=self.config.gestures)
        interaction_controller = InteractionController(config=self.config.gestures)
        system_controller = SystemIntentController(config=self.config.system)
        system_control_mode = ControlMode.POINTER
        system_window_action_mode = WindowActionMode.MOVE
        system_armed = self.config.system.mode is AppMode.SYSTEM_SHADOW or (
            self.config.system.mode is AppMode.SYSTEM_MACOS
            and self.config.system.enable_live_backend
            and self.config.system.start_armed
        )
        try:
            system_backend = self._build_system_backend()
        except RuntimeError as exc:
            print(f"AirDesk could not start: {exc}")
            return 1
        if system_backend is not None:
            system_backend.set_control_mode(system_control_mode)
        system_state = SystemControlState()
        interaction_state = InteractionState()
        window_manager = WindowManager()

        # Determine whether to use overlay mode (no camera preview)
        use_overlay = self.config.system.mode in (
            AppMode.SYSTEM_SHADOW,
            AppMode.SYSTEM_MACOS,
        )

        overlay = None
        renderer = None
        if not use_overlay:
            renderer = Renderer(config=self.config.render)

        print(self._startup_message(system_armed))

        try:
            camera_stream.open()
        except RuntimeError as exc:
            print(f"AirDesk could not start: {exc}")
            camera_stream.close()
            if overlay is not None:
                overlay.close()
            return 1

        return_code = 0
        try:
            if not use_overlay:
                cv2.namedWindow(self.window_title, cv2.WINDOW_NORMAL)

            hand_tracker = HandTracker(self.config.tracking)

            # Create overlay AFTER MediaPipe/OpenCV have initialized their
            # GPU contexts — otherwise NSApplication conflicts cause aborts.
            if use_overlay and overlay is None:
                try:
                    from airdesk.platform.overlay import OverlayWindow
                    screen_w, screen_h = self._get_screen_dimensions(system_backend)
                    overlay = OverlayWindow(screen_w, screen_h)
                except Exception as exc:
                    print(f"Overlay unavailable ({exc}), falling back to camera preview.")
                    use_overlay = False
                    renderer = Renderer(config=self.config.render)
                    cv2.namedWindow(self.window_title, cv2.WINDOW_NORMAL)
            while True:
                frame = camera_stream.read()
                hand_state = hand_tracker.detect(frame.image)
                gesture_state = gesture_engine.update(hand_state)
                if self.config.system.mode is AppMode.PROTOTYPE:
                    self._seed_windows(window_manager, frame.width, frame.height)
                    interaction_state = interaction_controller.update(
                        gesture_state,
                        window_manager,
                        interaction_state,
                        frame.width,
                        frame.height,
                    )
                else:
                    interaction_state = InteractionState()

                system_state = self._system_state_for_frame(
                    gesture_state,
                    frame.width,
                    frame.height,
                    system_controller,
                    system_backend,
                    system_armed,
                    system_control_mode,
                    system_window_action_mode,
                )

                if use_overlay and overlay is not None:
                    overlay.update(system_state)
                    # In overlay mode, use a very short cv2.waitKey on a
                    # dummy window just for key capture.  If the window
                    # doesn't exist yet, create a tiny one.
                    try:
                        key = cv2.waitKey(1) & 0xFF
                    except cv2.error:
                        key = 0xFF
                elif renderer is not None:
                    display_frame = renderer.render(
                        frame.image,
                        hand_state,
                        gesture_state,
                        window_manager.ordered_windows(),
                        interaction_state,
                        system_state=system_state,
                        app_mode=self.config.system.mode,
                    )
                    cv2.imshow(self.window_title, display_frame)
                    key = cv2.waitKey(1) & 0xFF
                else:
                    key = 0xFF
                if key in (27, ord("q")):
                    break
                if key in (ord("s"), ord("S")) and self.config.system.mode is AppMode.SYSTEM_MACOS:
                    system_armed = self._toggle_live_system_control(
                        system_armed,
                        system_controller,
                        system_backend,
                    )
                if key in (ord("w"), ord("W")) and self.config.system.mode is not AppMode.PROTOTYPE:
                    system_control_mode = self._toggle_system_control_mode(
                        system_control_mode,
                        system_backend,
                    )
                if key in (ord("r"), ord("R")) and self.config.system.mode is not AppMode.PROTOTYPE:
                    system_window_action_mode = self._toggle_system_window_action_mode(
                        system_control_mode,
                        system_window_action_mode,
                        system_backend,
                    )
                if key in (ord("c"), ord("C")) and self.config.system.mode is not AppMode.PROTOTYPE:
                    self._toggle_system_target_lock(
                        system_control_mode,
                        system_backend,
                    )
        except KeyboardInterrupt:
            print("\nAirDesk interrupted by user.")
        except (RuntimeError, cv2.error) as exc:
            print(f"AirDesk stopped unexpectedly: {exc}")
            return_code = 1
        finally:
            if overlay is not None:
                overlay.close()
            if system_backend is not None:
                system_backend.reset()
            if hand_tracker is not None:
                hand_tracker.close()
            camera_stream.close()
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
            print("AirDesk shutdown complete.")

        return return_code

    @staticmethod
    def _get_screen_dimensions(system_backend: SystemBackend | None) -> tuple[int, int]:
        """Detect the main display dimensions."""
        if isinstance(system_backend, MacOSSystemBackend) and system_backend.bridge is not None:
            bounds = system_backend.bridge.main_display_bounds()
            return int(bounds[2]), int(bounds[3])
        # Fallback: query CoreGraphics directly
        try:
            import ctypes
            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGMainDisplayID.restype = ctypes.c_uint32
            cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
            cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
            cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
            cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
            display_id = cg.CGMainDisplayID()
            return int(cg.CGDisplayPixelsWide(display_id)), int(cg.CGDisplayPixelsHigh(display_id))
        except Exception:
            return 1440, 900

    def _build_system_backend(self) -> SystemBackend | None:
        """Create the backend needed for the selected runtime mode."""
        if self.config.system.mode is AppMode.SYSTEM_SHADOW:
            return ShadowSystemBackend()
        if self.config.system.mode is AppMode.SYSTEM_MACOS and self.config.system.enable_live_backend:
            return MacOSSystemBackend()
        return None

    def _startup_message(self, system_armed: bool) -> str:
        """Return the startup banner for the selected runtime mode."""
        if self.config.system.mode is AppMode.SYSTEM_SHADOW:
            return (
                "Starting AirDesk system shadow mode. Press W for window mode, "
                "R to switch move and resize, C to lock a target, and Q or Esc to quit."
            )
        if self.config.system.mode is AppMode.SYSTEM_MACOS:
            if not self.config.system.enable_live_backend:
                return (
                    "Starting AirDesk macOS control mode in safety lock. "
                    "Relaunch with --enable-system-actions to arm live control."
                )
            if system_armed:
                return (
                    "Starting AirDesk macOS control mode armed. Press W for window mode, "
                    "R to switch move and resize, C to lock a target, S to disarm, "
                    "and Q or Esc to quit."
                )
            return (
                "Starting AirDesk macOS control mode disarmed. Press S to arm, "
                "W for window mode, R to switch move and resize, C to lock a target, "
                "and Q or Esc to quit."
            )
        return "Starting AirDesk in-app prototype. Press Q or Esc to quit."

    def _system_state_for_frame(
        self,
        gesture_state,
        frame_width: int,
        frame_height: int,
        system_controller: SystemIntentController,
        system_backend: SystemBackend | None,
        system_armed: bool,
        system_control_mode: ControlMode,
        system_window_action_mode: WindowActionMode,
    ) -> SystemControlState:
        """Resolve the current system-control state for the active runtime mode."""
        if self.config.system.mode is AppMode.PROTOTYPE:
            system_controller.enabled = False
            system_controller.reset()
            return SystemControlState()

        if self.config.system.mode is AppMode.SYSTEM_SHADOW:
            system_controller.enabled = True
            state = system_controller.update(gesture_state, frame_width, frame_height)
            state.armed = True
            state.control_mode = system_control_mode
            state.window_action_mode = system_window_action_mode
            if system_backend is not None:
                state = system_backend.apply(state)
            return state

        system_controller.enabled = False
        if not self.config.system.enable_live_backend:
            system_controller.reset()
            return SystemControlState(
                enabled=True,
                armed=False,
                backend_name="macos",
                control_mode=system_control_mode,
                window_action_mode=system_window_action_mode,
                phase=PointerPhase.IDLE,
                effect_label="Live control locked - relaunch with --enable-system-actions",
            )

        if not system_armed:
            system_controller.reset()
            return SystemControlState(
                enabled=True,
                armed=False,
                backend_name="macos",
                control_mode=system_control_mode,
                window_action_mode=system_window_action_mode,
                phase=PointerPhase.IDLE,
                effect_label="Live control disarmed - press S to arm",
            )

        system_controller.enabled = True
        state = system_controller.update(gesture_state, frame_width, frame_height)
        state.armed = True
        state.control_mode = system_control_mode
        state.window_action_mode = system_window_action_mode
        if system_backend is not None:
            state = system_backend.apply(state)
        return state

    def _toggle_live_system_control(
        self,
        system_armed: bool,
        system_controller: SystemIntentController,
        system_backend: SystemBackend | None,
    ) -> bool:
        """Arm or disarm live macOS control from the keyboard safety toggle."""
        if not self.config.system.enable_live_backend:
            print("Live macOS control is locked. Relaunch with --enable-system-actions first.")
            return system_armed

        if system_armed:
            system_controller.enabled = False
            system_controller.reset()
            if system_backend is not None:
                system_backend.reset()
            print("Live macOS control disarmed.")
            return False

        print("Live macOS control armed.")
        return True

    def _footer_text(self, system_armed: bool) -> str:
        """Return footer text for the active runtime mode."""
        if self.config.system.mode is AppMode.SYSTEM_SHADOW:
            return "AirDesk System Shadow | W mode | R move/resize | C lock | Q or Esc to quit"
        if self.config.system.mode is AppMode.SYSTEM_MACOS:
            if not self.config.system.enable_live_backend:
                return "AirDesk macOS Control | Relaunch with --enable-system-actions"
            toggle_label = "Disarm" if system_armed else "Arm"
            return (
                f"AirDesk macOS Control | S to {toggle_label} | W mode | R move/resize "
                "| C lock target | Open palm to steer | Q to quit"
            )
        return "AirDesk Prototype | Q or Esc to quit"

    def _toggle_system_control_mode(
        self,
        system_control_mode: ControlMode,
        system_backend: SystemBackend | None,
    ) -> ControlMode:
        """Switch between pointer control and focused-window control."""
        next_mode = ControlMode.WINDOW if system_control_mode is ControlMode.POINTER else ControlMode.POINTER
        if system_backend is not None:
            system_backend.set_control_mode(next_mode)
        print(f"System control switched to {next_mode.value} mode.")
        return next_mode

    def _toggle_system_window_action_mode(
        self,
        system_control_mode: ControlMode,
        system_window_action_mode: WindowActionMode,
        system_backend: SystemBackend | None,
    ) -> WindowActionMode:
        """Switch between moving and resizing the active window target."""
        if system_control_mode is not ControlMode.WINDOW:
            print("Switch to window mode before changing the window action.")
            return system_window_action_mode
        if system_backend is None:
            print("No system backend is active for window actions.")
            return system_window_action_mode
        message = system_backend.toggle_window_action_mode()
        if message is not None:
            print(message)
        return (
            WindowActionMode.RESIZE
            if system_window_action_mode is WindowActionMode.MOVE
            else WindowActionMode.MOVE
        )

    def _toggle_system_target_lock(
        self,
        system_control_mode: ControlMode,
        system_backend: SystemBackend | None,
    ) -> None:
        """Toggle a persistent target lock when supported by the backend."""
        if system_control_mode is not ControlMode.WINDOW:
            print("Switch to window mode before locking a target.")
            return
        if system_backend is None:
            print("No system backend is active for target locking.")
            return
        message = system_backend.toggle_target_lock()
        if message is not None:
            print(message)

    def _seed_windows(self, window_manager: WindowManager, frame_width: int, frame_height: int) -> None:
        """Create the initial in-app prototype panels once frame dimensions are known."""
        if window_manager.windows:
            return

        primary_width = min(300, max(frame_width // 2 - 30, 230))
        primary_height = 196
        secondary_width = min(268, max(frame_width // 3, 216))
        secondary_height = 168

        primary = VirtualWindow(
            id="air-panel-main",
            title="Air Panel",
            x=max((frame_width - primary_width) // 2 - 28, 28),
            y=max(frame_height // 7, 68),
            width=primary_width,
            height=primary_height,
            body_lines=(
                "Point with your index finger to hover.",
                "Pinch and drag to move any panel.",
                "Release the pinch to drop it in place.",
                "This is the core in-app prototype.",
            ),
        )
        notes = VirtualWindow(
            id="air-panel-notes",
            title="Gesture Notes",
            x=max(primary.x - 92, 20),
            y=min(primary.y + 118, max(frame_height - secondary_height - 24, 24)),
            width=secondary_width,
            height=secondary_height,
            body_lines=(
                "One hand tracked with MediaPipe.",
                "Cursor is smoothed with an EMA.",
                "Pinch uses normalized distance plus hysteresis.",
            ),
        )
        monitor = VirtualWindow(
            id="air-panel-monitor",
            title="Interaction Monitor",
            x=min(primary.x + primary.width - 84, max(frame_width - secondary_width - 20, 20)),
            y=min(primary.y + 52, max(frame_height - secondary_height - 24, 24)),
            width=secondary_width,
            height=secondary_height,
            body_lines=(
                "Topmost panel wins hover selection.",
                "Grabbed panels come to the front.",
                "Short hand-loss grace prevents accidental drops.",
            ),
        )

        for window in (notes, primary, monitor):
            window.clamp_within(frame_width, frame_height)
            window_manager.add_window(window)
