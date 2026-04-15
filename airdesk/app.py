"""Application shell for the AirDesk prototype."""

from dataclasses import dataclass, field

from airdesk.config import AppConfig, build_default_config
from airdesk.core.interaction_controller import InteractionController
from airdesk.core.window_manager import WindowManager
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.interaction import InteractionState
from airdesk.models.window import VirtualWindow
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
        interaction_state = InteractionState()
        window_manager = WindowManager()

        print("Starting AirDesk in-app prototype. Press Q or Esc to quit.")

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
                self._seed_windows(window_manager, frame.width, frame.height)
                hand_state = hand_tracker.detect(frame.image)
                gesture_state = gesture_engine.update(hand_state)
                interaction_state = interaction_controller.update(
                    gesture_state,
                    window_manager,
                    interaction_state,
                    frame.width,
                    frame.height,
                )
                display_frame = renderer.render(
                    frame.image,
                    hand_state,
                    gesture_state,
                    window_manager.ordered_windows(),
                    interaction_state,
                )
                footer_text = "AirDesk Prototype | Q or Esc to quit"
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
        except KeyboardInterrupt:
            print("\nAirDesk interrupted by user.")
        except (RuntimeError, cv2.error) as exc:
            print(f"AirDesk stopped unexpectedly: {exc}")
            return_code = 1
        finally:
            if hand_tracker is not None:
                hand_tracker.close()
            camera_stream.close()
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
            print("AirDesk shutdown complete.")

        return return_code

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
