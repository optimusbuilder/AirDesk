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
        interaction_controller = InteractionController()
        interaction_state = InteractionState()
        window_manager = WindowManager()

        print("Starting AirDesk Milestone 5 runtime. Press Q or Esc to quit.")

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
                )
                display_frame = renderer.render(
                    frame.image,
                    hand_state,
                    gesture_state,
                    window_manager.ordered_windows(),
                    interaction_state,
                )
                cv2.putText(
                    display_frame,
                    "AirDesk Milestone 5  |  Press Q or Esc to quit",
                    (16, frame.height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
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
        """Create the initial MVP panel once frame dimensions are known."""
        if window_manager.windows:
            return

        window_width = min(280, max(frame_width - 220, 220))
        window_height = min(170, max(frame_height - 260, 140))
        window_x = max((frame_width - window_width) // 2, 32)
        window_y = max(56, frame_height // 7)
        window_manager.add_window(
            VirtualWindow(
                id="air-panel-1",
                title="Air Panel",
                x=window_x,
                y=window_y,
                width=window_width,
                height=window_height,
                body_lines=(
                    "Hover with the fingertip cursor.",
                    "Pinch-to-grab arrives in Milestone 6.",
                    "This panel is fully in-app for now.",
                ),
            )
        )
