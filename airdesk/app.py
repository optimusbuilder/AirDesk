"""Application shell for the AirDesk prototype."""

from dataclasses import dataclass, field

from airdesk.config import AppConfig, AppMode, build_default_config
from airdesk.core.interaction_controller import InteractionController
from airdesk.core.window_manager import WindowManager
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow
from airdesk.platform.base import SystemBackend
from airdesk.platform.macos import MacOSSystemBackend
from airdesk.platform.shadow import ShadowSystemBackend
from airdesk.system.controller import SystemIntentController
from airdesk.system.intents import PointerPhase, SystemControlState
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
        renderer = Renderer(config=self.config.render)
        gesture_engine = GestureEngine(config=self.config.gestures)
        interaction_controller = InteractionController(config=self.config.gestures)
        system_controller = SystemIntentController(config=self.config.system)
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
        system_state = SystemControlState()
        interaction_state = InteractionState()
        window_manager = WindowManager()

        print(self._startup_message(system_armed))

        try:
            camera_stream.open()
        except RuntimeError as exc:
            print(f"AirDesk could not start: {exc}")
            camera_stream.close()
            return 1

        return_code = 0
        try:
            cv2.namedWindow(self.window_title, cv2.WINDOW_NORMAL)
            hand_tracker = HandTracker(self.config.tracking)
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
                )

                display_frame = renderer.render(
                    frame.image,
                    hand_state,
                    gesture_state,
                    window_manager.ordered_windows(),
                    interaction_state,
                    system_state=system_state,
                    app_mode=self.config.system.mode,
                )
                footer_text = self._footer_text(system_armed)
                (footer_width, _), _ = cv2.getTextSize(
                    footer_text,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    1,
                )
                footer_x = max(frame.width - footer_width - 18, 18)
                cv2.putText(
                    display_frame,
                    footer_text,
                    (footer_x, frame.height - 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.imshow(self.window_title, display_frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if key in (ord("s"), ord("S")) and self.config.system.mode is AppMode.SYSTEM_MACOS:
                    system_armed = self._toggle_live_system_control(
                        system_armed,
                        system_controller,
                        system_backend,
                    )
        except KeyboardInterrupt:
            print("\nAirDesk interrupted by user.")
        except (RuntimeError, cv2.error) as exc:
            print(f"AirDesk stopped unexpectedly: {exc}")
            return_code = 1
        finally:
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
            return "Starting AirDesk system shadow mode. Press Q or Esc to quit."
        if self.config.system.mode is AppMode.SYSTEM_MACOS:
            if not self.config.system.enable_live_backend:
                return (
                    "Starting AirDesk macOS control mode in safety lock. "
                    "Relaunch with --enable-system-actions to arm live control."
                )
            if system_armed:
                return "Starting AirDesk macOS control mode armed. Press S to disarm. Press Q or Esc to quit."
            return "Starting AirDesk macOS control mode disarmed. Press S to arm. Press Q or Esc to quit."
        return "Starting AirDesk in-app prototype. Press Q or Esc to quit."

    def _system_state_for_frame(
        self,
        gesture_state,
        frame_width: int,
        frame_height: int,
        system_controller: SystemIntentController,
        system_backend: SystemBackend | None,
        system_armed: bool,
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
                phase=PointerPhase.IDLE,
                effect_label="Live control locked - relaunch with --enable-system-actions",
            )

        if not system_armed:
            system_controller.reset()
            return SystemControlState(
                enabled=True,
                armed=False,
                backend_name="macos",
                phase=PointerPhase.IDLE,
                effect_label="Live control disarmed - press S to arm",
            )

        system_controller.enabled = True
        state = system_controller.update(gesture_state, frame_width, frame_height)
        state.armed = True
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
            return "AirDesk System Shadow | Q or Esc to quit"
        if self.config.system.mode is AppMode.SYSTEM_MACOS:
            if not self.config.system.enable_live_backend:
                return "AirDesk macOS Control | Relaunch with --enable-system-actions"
            toggle_label = "Disarm" if system_armed else "Arm"
            return f"AirDesk macOS Control | S to {toggle_label} | Open palm to steer | Q to quit"
        return "AirDesk Prototype | Q or Esc to quit"

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
