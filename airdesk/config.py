"""Configuration models for AirDesk."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """Webcam and frame settings."""

    device_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    mirror_output: bool = True


@dataclass(frozen=True, slots=True)
class TrackingConfig:
    """MediaPipe hand tracking settings."""

    max_num_hands: int = 1
    min_detection_confidence: float = 0.60
    min_tracking_confidence: float = 0.60


@dataclass(frozen=True, slots=True)
class GestureConfig:
    """Gesture detection and smoothing settings."""

    cursor_smoothing_alpha: float = 0.40
    pinch_on_threshold: float = 0.30
    pinch_off_threshold: float = 0.40
    hand_loss_timeout_ms: int = 150


@dataclass(frozen=True, slots=True)
class RenderConfig:
    """Rendering and debug overlay settings."""

    window_border_thickness: int = 2
    window_corner_radius: int = 8
    cursor_radius: int = 8
    show_debug_hud: bool = True


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level application configuration."""

    camera: CameraConfig = CameraConfig()
    tracking: TrackingConfig = TrackingConfig()
    gestures: GestureConfig = GestureConfig()
    render: RenderConfig = RenderConfig()


def build_default_config() -> AppConfig:
    """Return the default application configuration."""
    return AppConfig()
