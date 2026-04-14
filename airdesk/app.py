"""Application shell for the AirDesk prototype."""

from dataclasses import dataclass, field

from airdesk.config import AppConfig, build_default_config
from airdesk.gestures.gesture_engine import GestureEngine
from airdesk.models.interaction import InteractionState
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
        interaction_state = InteractionState()
        windows = []

        print("Starting AirDesk Milestone 4 runtime. Press Q or Esc to quit.")

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
                display_frame = renderer.render(
                    frame.image,
                    hand_state,
                    gesture_state,
                    windows,
                    interaction_state,
                )
                cv2.putText(
                    display_frame,
                    "AirDesk Milestone 4  |  Press Q or Esc to quit",
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
