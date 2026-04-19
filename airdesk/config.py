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
    SYSTEM_MACOS = "system-macos"


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
    cursor_filter_min_cutoff: float = 1.0
    cursor_filter_beta: float = 0.007
    cursor_filter_d_cutoff: float = 1.0
    pinch_on_threshold: float = 0.30
    pinch_off_threshold: float = 0.40
    pinch_debounce_ms: int = 40
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
    enable_live_backend: bool = False
    start_armed: bool = False
    clutch_activation_ms: int = 180
    pinch_press_delay_ms: int = 200
    tap_click_max_movement_px: int = 32
    double_click_window_ms: int = 450
    double_click_max_movement_px: int = 40
    cursor_edge_padding: float = 0.08
    cursor_sensitivity: float = 1.18
    cursor_deadzone_px: int = 6


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
