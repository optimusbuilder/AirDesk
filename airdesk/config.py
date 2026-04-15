"""Configuration models for AirDesk."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_HAND_LANDMARKER_PATH = PACKAGE_ROOT / "assets" / "hand_landmarker.task"


class AppMode(StrEnum):
    """Top-level runtime mode for the AirDesk app."""

    PROTOTYPE = "prototype"
    SYSTEM_SHADOW = "system-shadow"


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

    model_asset_path: str = str(DEFAULT_HAND_LANDMARKER_PATH)
    max_num_hands: int = 1
    min_detection_confidence: float = 0.60
    min_hand_presence_confidence: float = 0.60
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
class SystemControlConfig:
    """System-control mode configuration."""

    mode: AppMode = AppMode.PROTOTYPE


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level application configuration."""

    camera: CameraConfig = CameraConfig()
    tracking: TrackingConfig = TrackingConfig()
    gestures: GestureConfig = GestureConfig()
    render: RenderConfig = RenderConfig()
    system: SystemControlConfig = SystemControlConfig()


def build_default_config() -> AppConfig:
    """Return the default application configuration."""
    return AppConfig()
