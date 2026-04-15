"""Live macOS backend for real system pointer control."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass, field
from typing import Protocol

from airdesk.platform.base import SystemBackend
from airdesk.system.intents import NormalizedPoint, PointerPhase, SystemControlState


ScreenPoint = tuple[float, float]

_KCG_HID_EVENT_TAP = 0
_KCG_EVENT_LEFT_MOUSE_DOWN = 1
_KCG_EVENT_LEFT_MOUSE_UP = 2
_KCG_EVENT_MOUSE_MOVED = 5
_KCG_EVENT_LEFT_MOUSE_DRAGGED = 6
_KCG_MOUSE_BUTTON_LEFT = 0


class _CGPoint(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
    ]


class _CGSize(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]


class _CGRect(ctypes.Structure):
    _fields_ = [
        ("origin", _CGPoint),
        ("size", _CGSize),
    ]


class CoreGraphicsBridge(Protocol):
    """Minimal bridge interface for posting macOS pointer events."""

    def accessibility_is_trusted(self) -> bool: ...

    def main_display_bounds(self) -> tuple[float, float, float, float]: ...

    def move_cursor(self, point: ScreenPoint) -> None: ...

    def post_primary_down(self, point: ScreenPoint) -> None: ...

    def post_primary_drag(self, point: ScreenPoint) -> None: ...

    def post_primary_up(self, point: ScreenPoint) -> None: ...


class QuartzCoreGraphicsBridge:
    """ctypes wrapper around the small CoreGraphics surface we need."""

    def __init__(self) -> None:
        application_services_path = (
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        core_foundation_path = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        self._application_services = ctypes.CDLL(application_services_path)
        self._core_foundation = ctypes.CDLL(core_foundation_path)
        self._configure_signatures()

    def accessibility_is_trusted(self) -> bool:
        return bool(self._application_services.AXIsProcessTrusted())

    def main_display_bounds(self) -> tuple[float, float, float, float]:
        display_id = self._application_services.CGMainDisplayID()
        bounds = self._application_services.CGDisplayBounds(display_id)
        return (
            bounds.origin.x,
            bounds.origin.y,
            bounds.size.width,
            bounds.size.height,
        )

    def move_cursor(self, point: ScreenPoint) -> None:
        self._warp_cursor(point)
        self._post_mouse_event(_KCG_EVENT_MOUSE_MOVED, point)

    def post_primary_down(self, point: ScreenPoint) -> None:
        self._warp_cursor(point)
        self._post_mouse_event(_KCG_EVENT_LEFT_MOUSE_DOWN, point)

    def post_primary_drag(self, point: ScreenPoint) -> None:
        self._warp_cursor(point)
        self._post_mouse_event(_KCG_EVENT_LEFT_MOUSE_DRAGGED, point)

    def post_primary_up(self, point: ScreenPoint) -> None:
        self._warp_cursor(point)
        self._post_mouse_event(_KCG_EVENT_LEFT_MOUSE_UP, point)

    def _configure_signatures(self) -> None:
        self._application_services.AXIsProcessTrusted.argtypes = []
        self._application_services.AXIsProcessTrusted.restype = ctypes.c_bool

        self._application_services.CGMainDisplayID.argtypes = []
        self._application_services.CGMainDisplayID.restype = ctypes.c_uint32

        self._application_services.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        self._application_services.CGDisplayBounds.restype = _CGRect

        self._application_services.CGWarpMouseCursorPosition.argtypes = [_CGPoint]
        self._application_services.CGWarpMouseCursorPosition.restype = ctypes.c_int32

        self._application_services.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            _CGPoint,
            ctypes.c_uint32,
        ]
        self._application_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p

        self._application_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._application_services.CGEventPost.restype = None

        self._core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self._core_foundation.CFRelease.restype = None

    def _warp_cursor(self, point: ScreenPoint) -> None:
        error_code = self._application_services.CGWarpMouseCursorPosition(_CGPoint(*point))
        if error_code != 0:
            raise RuntimeError(f"CGWarpMouseCursorPosition failed with code {error_code}")

    def _post_mouse_event(self, mouse_type: int, point: ScreenPoint) -> None:
        event = self._application_services.CGEventCreateMouseEvent(
            None,
            mouse_type,
            _CGPoint(*point),
            _KCG_MOUSE_BUTTON_LEFT,
        )
        if not event:
            raise RuntimeError("CGEventCreateMouseEvent returned null")

        try:
            self._application_services.CGEventPost(_KCG_HID_EVENT_TAP, event)
        finally:
            self._core_foundation.CFRelease(event)


@dataclass(slots=True)
class MacOSSystemBackend(SystemBackend):
    """Real macOS pointer backend driven by backend-agnostic system intents."""

    name: str = "macos"
    bridge: CoreGraphicsBridge | None = None
    _button_down: bool = field(default=False, init=False, repr=False)
    _last_screen_cursor: ScreenPoint | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.bridge is not None:
            return
        if sys.platform != "darwin":
            raise RuntimeError("Live macOS control is only available on macOS.")
        self.bridge = QuartzCoreGraphicsBridge()

    def apply(self, state: SystemControlState) -> SystemControlState:
        """Apply one frame of live macOS pointer intent."""
        state.backend_name = self.name

        if not self.bridge.accessibility_is_trusted():
            state.permission_granted = False
            state.effect_label = (
                "Grant Accessibility access to this Python app or terminal to enable live control"
            )
            return state
        state.permission_granted = True

        screen_point = self._screen_point_for_state(state)
        if screen_point is not None:
            self._last_screen_cursor = screen_point

        if state.phase is PointerPhase.LOST:
            state.effect_label = "Live macOS control waiting for one tracked hand"
            return state
        if state.phase is PointerPhase.IDLE:
            return state

        if state.phase is PointerPhase.PRESS and screen_point is not None:
            self.bridge.post_primary_down(screen_point)
            self._button_down = True
            state.effect_label = self._describe("press", screen_point)
            return state

        if state.phase is PointerPhase.DRAG and screen_point is not None:
            if not self._button_down:
                self.bridge.post_primary_down(screen_point)
            self.bridge.post_primary_drag(screen_point)
            self._button_down = True
            state.effect_label = self._describe("drag", screen_point)
            return state

        if state.phase is PointerPhase.RELEASE:
            if self._button_down and screen_point is not None:
                self.bridge.post_primary_up(screen_point)
            self._button_down = False
            state.effect_label = (
                self._describe("release", screen_point)
                if screen_point is not None
                else "Live macOS control released after tracking loss"
            )
            return state

        if state.phase is PointerPhase.MOVE and screen_point is not None:
            self.bridge.move_cursor(screen_point)
            state.effect_label = self._describe("move", screen_point)
            return state

        state.effect_label = "Live macOS control armed"
        return state

    def reset(self) -> None:
        """Release the primary button if the backend is disarmed mid-drag."""
        if self.bridge is None:
            return
        if not self._button_down:
            return
        if not self.bridge.accessibility_is_trusted():
            self._button_down = False
            return
        if self._last_screen_cursor is not None:
            self.bridge.post_primary_up(self._last_screen_cursor)
        self._button_down = False

    def _screen_point_for_state(self, state: SystemControlState) -> ScreenPoint | None:
        if state.normalized_cursor is not None:
            return self._normalized_to_screen(state.normalized_cursor)
        if state.phase is PointerPhase.RELEASE:
            return self._last_screen_cursor
        return None

    def _normalized_to_screen(self, cursor: NormalizedPoint) -> ScreenPoint:
        origin_x, origin_y, width, height = self.bridge.main_display_bounds()
        usable_width = max(width - 1.0, 1.0)
        usable_height = max(height - 1.0, 1.0)
        normalized_x = min(max(cursor[0], 0.0), 1.0)
        normalized_y = min(max(cursor[1], 0.0), 1.0)
        return (
            round(origin_x + (normalized_x * usable_width)),
            round(origin_y + (normalized_y * usable_height)),
        )

    @staticmethod
    def _describe(action: str, point: ScreenPoint | None) -> str:
        if point is None:
            return f"Live macOS {action}"
        x, y = point
        return f"Live macOS {action} at {int(x)}, {int(y)}"
