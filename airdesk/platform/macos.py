"""Live macOS backend for real system pointer control."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass, field
from typing import Protocol

from airdesk.platform.base import SystemBackend
from airdesk.system.intents import (
    ControlMode,
    NormalizedPoint,
    PointerPhase,
    SystemControlState,
    WindowActionMode,
)


ScreenPoint = tuple[float, float]
WindowBounds = tuple[float, float, float, float]
WindowRef = object
ResizeAnchor = tuple[str, str]

_KCG_HID_EVENT_TAP = 0
_KCG_EVENT_LEFT_MOUSE_DOWN = 1
_KCG_EVENT_LEFT_MOUSE_UP = 2
_KCG_EVENT_MOUSE_MOVED = 5
_KCG_EVENT_LEFT_MOUSE_DRAGGED = 6
_KCG_MOUSE_BUTTON_LEFT = 0
_KCG_MOUSE_EVENT_CLICK_STATE = 1
_KAX_VALUE_TYPE_CGPOINT = 1
_KAX_VALUE_TYPE_CGSIZE = 2
_KCF_STRING_ENCODING_UTF8 = 0x08000100
_KAX_ERROR_SUCCESS = 0
_MIN_WINDOW_WIDTH = 320.0
_MIN_WINDOW_HEIGHT = 220.0
_SNAP_THRESHOLD_RATIO = 0.08


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
    """Bridge interface for CoreGraphics pointer control and AX window control."""

    def accessibility_is_trusted(self) -> bool: ...

    def main_display_bounds(self) -> tuple[float, float, float, float]: ...

    def move_cursor(self, point: ScreenPoint) -> None: ...

    def post_primary_down(self, point: ScreenPoint) -> None: ...

    def post_primary_drag(self, point: ScreenPoint) -> None: ...

    def post_primary_up(self, point: ScreenPoint) -> None: ...

    def post_primary_click(self, point: ScreenPoint, click_count: int = 1) -> None: ...

    def copy_focused_window(self) -> WindowRef | None: ...

    def release_ref(self, ref: WindowRef | None) -> None: ...

    def copy_window_title(self, window_ref: WindowRef) -> str | None: ...

    def copy_window_bounds(self, window_ref: WindowRef) -> WindowBounds | None: ...

    def is_window_position_settable(self, window_ref: WindowRef) -> bool: ...

    def is_window_size_settable(self, window_ref: WindowRef) -> bool: ...

    def window_pid(self, window_ref: WindowRef) -> int | None: ...

    def move_window_to(self, window_ref: WindowRef, origin: ScreenPoint) -> None: ...

    def resize_window_to(self, window_ref: WindowRef, size: tuple[float, float]) -> None: ...


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
        self._system_wide_element = self._application_services.AXUIElementCreateSystemWide()
        self._focused_application_attr = self._create_cfstring("AXFocusedApplication")
        self._focused_window_attr = self._create_cfstring("AXFocusedWindow")
        self._title_attr = self._create_cfstring("AXTitle")
        self._position_attr = self._create_cfstring("AXPosition")
        self._size_attr = self._create_cfstring("AXSize")

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

    def post_primary_click(self, point: ScreenPoint, click_count: int = 1) -> None:
        self._warp_cursor(point)
        self._post_mouse_event(
            _KCG_EVENT_LEFT_MOUSE_DOWN,
            point,
            click_count=max(click_count, 1),
        )
        self._post_mouse_event(
            _KCG_EVENT_LEFT_MOUSE_UP,
            point,
            click_count=max(click_count, 1),
        )

    def copy_focused_window(self) -> WindowRef | None:
        focused_app = self._copy_attribute_value(
            self._system_wide_element,
            self._focused_application_attr,
        )
        if focused_app is None:
            return None

        try:
            return self._copy_attribute_value(focused_app, self._focused_window_attr)
        finally:
            self.release_ref(focused_app)

    def release_ref(self, ref: WindowRef | None) -> None:
        if ref is None:
            return
        self._core_foundation.CFRelease(ref)

    def copy_window_title(self, window_ref: WindowRef) -> str | None:
        title_ref = self._copy_attribute_value(window_ref, self._title_attr)
        if title_ref is None:
            return None

        try:
            return self._cfstring_to_python(title_ref)
        finally:
            self.release_ref(title_ref)

    def copy_window_bounds(self, window_ref: WindowRef) -> WindowBounds | None:
        position_ref = self._copy_attribute_value(window_ref, self._position_attr)
        size_ref = self._copy_attribute_value(window_ref, self._size_attr)
        if position_ref is None or size_ref is None:
            self.release_ref(position_ref)
            self.release_ref(size_ref)
            return None

        try:
            point = _CGPoint()
            size = _CGSize()
            if not self._application_services.AXValueGetValue(
                position_ref,
                _KAX_VALUE_TYPE_CGPOINT,
                ctypes.byref(point),
            ):
                return None
            if not self._application_services.AXValueGetValue(
                size_ref,
                _KAX_VALUE_TYPE_CGSIZE,
                ctypes.byref(size),
            ):
                return None
            return (point.x, point.y, size.width, size.height)
        finally:
            self.release_ref(position_ref)
            self.release_ref(size_ref)

    def is_window_position_settable(self, window_ref: WindowRef) -> bool:
        settable = ctypes.c_bool(False)
        error_code = self._application_services.AXUIElementIsAttributeSettable(
            window_ref,
            self._position_attr,
            ctypes.byref(settable),
        )
        return error_code == _KAX_ERROR_SUCCESS and bool(settable.value)

    def is_window_size_settable(self, window_ref: WindowRef) -> bool:
        settable = ctypes.c_bool(False)
        error_code = self._application_services.AXUIElementIsAttributeSettable(
            window_ref,
            self._size_attr,
            ctypes.byref(settable),
        )
        return error_code == _KAX_ERROR_SUCCESS and bool(settable.value)

    def window_pid(self, window_ref: WindowRef) -> int | None:
        pid = ctypes.c_int()
        error_code = self._application_services.AXUIElementGetPid(window_ref, ctypes.byref(pid))
        if error_code != _KAX_ERROR_SUCCESS:
            return None
        return int(pid.value)

    def move_window_to(self, window_ref: WindowRef, origin: ScreenPoint) -> None:
        point = _CGPoint(*origin)
        position_value = self._application_services.AXValueCreate(
            _KAX_VALUE_TYPE_CGPOINT,
            ctypes.byref(point),
        )
        if not position_value:
            raise RuntimeError("AXValueCreate returned null for window position")

        try:
            error_code = self._application_services.AXUIElementSetAttributeValue(
                window_ref,
                self._position_attr,
                position_value,
            )
            if error_code != _KAX_ERROR_SUCCESS:
                raise RuntimeError(f"AXUIElementSetAttributeValue failed with code {error_code}")
        finally:
            self.release_ref(position_value)

    def resize_window_to(self, window_ref: WindowRef, size: tuple[float, float]) -> None:
        cg_size = _CGSize(*size)
        size_value = self._application_services.AXValueCreate(
            _KAX_VALUE_TYPE_CGSIZE,
            ctypes.byref(cg_size),
        )
        if not size_value:
            raise RuntimeError("AXValueCreate returned null for window size")

        try:
            error_code = self._application_services.AXUIElementSetAttributeValue(
                window_ref,
                self._size_attr,
                size_value,
            )
            if error_code != _KAX_ERROR_SUCCESS:
                raise RuntimeError(f"AXUIElementSetAttributeValue failed with code {error_code}")
        finally:
            self.release_ref(size_value)

    def _configure_signatures(self) -> None:
        self._application_services.AXIsProcessTrusted.argtypes = []
        self._application_services.AXIsProcessTrusted.restype = ctypes.c_bool

        self._application_services.AXUIElementCreateSystemWide.argtypes = []
        self._application_services.AXUIElementCreateSystemWide.restype = ctypes.c_void_p

        self._application_services.AXUIElementCopyAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._application_services.AXUIElementCopyAttributeValue.restype = ctypes.c_int32

        self._application_services.AXUIElementIsAttributeSettable.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_bool),
        ]
        self._application_services.AXUIElementIsAttributeSettable.restype = ctypes.c_int32

        self._application_services.AXUIElementSetAttributeValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._application_services.AXUIElementSetAttributeValue.restype = ctypes.c_int32

        self._application_services.AXUIElementGetPid.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._application_services.AXUIElementGetPid.restype = ctypes.c_int32

        self._application_services.AXValueCreate.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._application_services.AXValueCreate.restype = ctypes.c_void_p

        self._application_services.AXValueGetValue.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        self._application_services.AXValueGetValue.restype = ctypes.c_bool

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

        self._application_services.CGEventSetIntegerValueField.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_int64,
        ]
        self._application_services.CGEventSetIntegerValueField.restype = None

        self._core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self._core_foundation.CFRelease.restype = None

        self._core_foundation.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        self._core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p

        self._core_foundation.CFStringGetLength.argtypes = [ctypes.c_void_p]
        self._core_foundation.CFStringGetLength.restype = ctypes.c_long

        self._core_foundation.CFStringGetMaximumSizeForEncoding.argtypes = [
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        self._core_foundation.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long

        self._core_foundation.CFStringGetCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        self._core_foundation.CFStringGetCString.restype = ctypes.c_bool

    def _warp_cursor(self, point: ScreenPoint) -> None:
        error_code = self._application_services.CGWarpMouseCursorPosition(_CGPoint(*point))
        if error_code != 0:
            raise RuntimeError(f"CGWarpMouseCursorPosition failed with code {error_code}")

    def _post_mouse_event(
        self,
        mouse_type: int,
        point: ScreenPoint,
        click_count: int = 1,
    ) -> None:
        event = self._application_services.CGEventCreateMouseEvent(
            None,
            mouse_type,
            _CGPoint(*point),
            _KCG_MOUSE_BUTTON_LEFT,
        )
        if not event:
            raise RuntimeError("CGEventCreateMouseEvent returned null")

        try:
            self._application_services.CGEventSetIntegerValueField(
                event,
                _KCG_MOUSE_EVENT_CLICK_STATE,
                click_count,
            )
            self._application_services.CGEventPost(_KCG_HID_EVENT_TAP, event)
        finally:
            self._core_foundation.CFRelease(event)

    def _create_cfstring(self, value: str) -> ctypes.c_void_p:
        ref = self._core_foundation.CFStringCreateWithCString(
            None,
            value.encode("utf-8"),
            _KCF_STRING_ENCODING_UTF8,
        )
        if not ref:
            raise RuntimeError(f"CFStringCreateWithCString failed for {value!r}")
        return ref

    def _cfstring_to_python(self, cfstring_ref: ctypes.c_void_p) -> str | None:
        length = self._core_foundation.CFStringGetLength(cfstring_ref)
        buffer_size = self._core_foundation.CFStringGetMaximumSizeForEncoding(
            length,
            _KCF_STRING_ENCODING_UTF8,
        ) + 1
        buffer = ctypes.create_string_buffer(buffer_size)
        success = self._core_foundation.CFStringGetCString(
            cfstring_ref,
            buffer,
            buffer_size,
            _KCF_STRING_ENCODING_UTF8,
        )
        if not success:
            return None
        return buffer.value.decode("utf-8")

    def _copy_attribute_value(
        self,
        element: ctypes.c_void_p,
        attribute_ref: ctypes.c_void_p,
    ) -> ctypes.c_void_p | None:
        value = ctypes.c_void_p()
        error_code = self._application_services.AXUIElementCopyAttributeValue(
            element,
            attribute_ref,
            ctypes.byref(value),
        )
        if error_code != _KAX_ERROR_SUCCESS:
            return None
        return value.value

    def __del__(self) -> None:
        for ref in (
            getattr(self, "_focused_application_attr", None),
            getattr(self, "_focused_window_attr", None),
            getattr(self, "_title_attr", None),
            getattr(self, "_position_attr", None),
            getattr(self, "_size_attr", None),
            getattr(self, "_system_wide_element", None),
        ):
            try:
                self.release_ref(ref)
            except Exception:
                pass


@dataclass(slots=True)
class MacOSSystemBackend(SystemBackend):
    """Real macOS pointer backend driven by backend-agnostic system intents."""

    name: str = "macos"
    bridge: CoreGraphicsBridge | None = None
    control_mode: ControlMode = ControlMode.POINTER
    window_action_mode: WindowActionMode = WindowActionMode.MOVE
    _button_down: bool = field(default=False, init=False, repr=False)
    _last_screen_cursor: ScreenPoint | None = field(default=None, init=False, repr=False)
    _locked_window_ref: WindowRef | None = field(default=None, init=False, repr=False)
    _locked_window_title: str | None = field(default=None, init=False, repr=False)
    _active_window_origin: ScreenPoint | None = field(default=None, init=False, repr=False)
    _active_window_bounds: WindowBounds | None = field(default=None, init=False, repr=False)
    _window_drag_anchor: ScreenPoint | None = field(default=None, init=False, repr=False)
    _resize_anchor: ResizeAnchor | None = field(default=None, init=False, repr=False)
    _process_pid: int = field(default_factory=os.getpid, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.bridge is not None:
            return
        if sys.platform != "darwin":
            raise RuntimeError("Live macOS control is only available on macOS.")
        self.bridge = QuartzCoreGraphicsBridge()

    def apply(self, state: SystemControlState) -> SystemControlState:
        """Apply one frame of live macOS pointer intent."""
        state.backend_name = self.name
        state.control_mode = self.control_mode
        state.window_action_mode = self.window_action_mode

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

        if self.control_mode is ControlMode.WINDOW:
            return self._apply_window_mode(state, screen_point)

        if state.phase is PointerPhase.LOST:
            state.effect_label = "Live macOS control waiting for one tracked hand"
            return state
        if state.phase is PointerPhase.IDLE:
            return state

        if state.phase is PointerPhase.CLICK and screen_point is not None:
            click_count = max(state.click_count, 1)
            self.bridge.post_primary_click(screen_point, click_count=click_count)
            self._button_down = False
            action_label = "double-click" if click_count == 2 else "click"
            state.effect_label = self._describe(action_label, screen_point)
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
        if self._button_down:
            if self.bridge.accessibility_is_trusted() and self._last_screen_cursor is not None:
                self.bridge.post_primary_up(self._last_screen_cursor)
            self._button_down = False
        self._clear_window_drag_state()

    def set_control_mode(self, control_mode: ControlMode) -> None:
        """Switch between pointer mode and focused-window move mode."""
        if control_mode is self.control_mode:
            return
        self.reset()
        self.control_mode = control_mode

    def toggle_target_lock(self) -> str | None:
        """Toggle a persistent focused-window target for window mode."""
        if self.control_mode is not ControlMode.WINDOW:
            return "Switch to window mode before locking a target."
        if self._locked_window_ref is not None:
            title = self._locked_window_title or "Focused window"
            self._clear_window_target()
            return f'Cleared locked window target "{title}".'

        lock_result = self._lock_focused_window_target()
        if lock_result is None:
            return "No focused window is available to lock"
        if isinstance(lock_result, str):
            return lock_result

        _, title, _ = lock_result
        return f'Locked "{title}" as the window target.'

    def toggle_window_action_mode(self) -> str | None:
        """Toggle between moving and resizing the active window target."""
        if self.control_mode is not ControlMode.WINDOW:
            return "Switch to window mode before changing the window action."
        self._clear_window_drag_state()
        next_mode = (
            WindowActionMode.RESIZE
            if self.window_action_mode is WindowActionMode.MOVE
            else WindowActionMode.MOVE
        )
        self.window_action_mode = next_mode
        return f"Window action switched to {next_mode.value}."

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

    def _apply_window_mode(
        self,
        state: SystemControlState,
        screen_point: ScreenPoint | None,
    ) -> SystemControlState:
        state.window_action_mode = self.window_action_mode
        state.target_label = self._locked_window_title or self._focused_window_title()
        state.target_locked = self._locked_window_ref is not None

        if state.phase is PointerPhase.LOST:
            state.effect_label = "Window mode waiting for one tracked hand"
            return state
        if state.phase is PointerPhase.IDLE:
            state.effect_label = self._window_idle_label(state)
            return state
        if state.phase is PointerPhase.MOVE:
            state.effect_label = self._window_ready_label(state)
            return state
        if state.phase is PointerPhase.CLICK:
            if state.click_count == 2:
                ignored_label = "Quick double tap ignored"
            else:
                ignored_label = "Quick tap ignored"
            if state.target_locked and state.target_label is not None:
                state.effect_label = f'{ignored_label} while "{state.target_label}" is locked'
            else:
                state.effect_label = f"{ignored_label} in window mode"
            return state
        if state.phase is PointerPhase.PRESS:
            return self._begin_window_action(state, screen_point)
        if state.phase is PointerPhase.DRAG:
            if self.window_action_mode is WindowActionMode.RESIZE:
                return self._resize_active_window(state, screen_point)
            return self._move_active_window(state, screen_point)
        if state.phase is PointerPhase.RELEASE:
            return self._release_active_window(state, screen_point)
        return state

    def _begin_window_action(
        self,
        state: SystemControlState,
        screen_point: ScreenPoint | None,
    ) -> SystemControlState:
        target = self._locked_window_target()
        if target is None:
            lock_result = self._lock_focused_window_target()
            if lock_result is None:
                state.effect_label = (
                    f"No focused window is available to {self.window_action_mode.value}"
                )
                return state
            if isinstance(lock_result, str):
                state.effect_label = lock_result
                return state
            target = lock_result

        window_ref, title, window_bounds = target
        if screen_point is None:
            state.target_label = title
            state.target_locked = self._locked_window_ref is not None
            state.effect_label = "Could not read the cursor position for window control"
            return state

        state.target_label = title
        state.target_locked = self._locked_window_ref is not None
        if self.window_action_mode is WindowActionMode.RESIZE:
            if not self.bridge.is_window_size_settable(window_ref):
                state.effect_label = f'"{title}" cannot be resized through Accessibility'
                return state
            self._active_window_bounds = window_bounds
            self._window_drag_anchor = screen_point
            self._resize_anchor = self._resize_anchor_for_point(screen_point, window_bounds)
            anchor_label = self._format_resize_anchor(self._resize_anchor)
            state.effect_label = f'Grabbed {anchor_label} corner of "{title}" for resize'
            return state

        self._active_window_origin = (window_bounds[0], window_bounds[1])
        self._active_window_bounds = window_bounds
        self._window_drag_anchor = screen_point
        state.effect_label = f'Grabbed "{title}" for movement'
        return state

    def _move_active_window(
        self,
        state: SystemControlState,
        screen_point: ScreenPoint | None,
    ) -> SystemControlState:
        if self._locked_window_ref is None or self._active_window_origin is None:
            return self._begin_window_action(state, screen_point)
        if screen_point is None or self._window_drag_anchor is None:
            state.effect_label = "Waiting for a stable cursor to move the focused window"
            return state

        delta_x = screen_point[0] - self._window_drag_anchor[0]
        delta_y = screen_point[1] - self._window_drag_anchor[1]
        target_origin = (
            round(self._active_window_origin[0] + delta_x),
            round(self._active_window_origin[1] + delta_y),
        )
        self.bridge.move_window_to(self._locked_window_ref, target_origin)
        state.target_label = self._locked_window_title
        state.target_locked = self._locked_window_ref is not None
        snap_candidate = self._snap_candidate_for_point(screen_point)
        if snap_candidate is not None and self.bridge.is_window_size_settable(self._locked_window_ref):
            snap_label, _, _ = snap_candidate
            state.effect_label = (
                f'Release to snap "{self._locked_window_title or "Focused window"}" {snap_label}'
            )
        else:
            state.effect_label = (
                f'Moving "{self._locked_window_title or "Focused window"}" to '
                f'{int(target_origin[0])}, {int(target_origin[1])}'
            )
        return state

    def _resize_active_window(
        self,
        state: SystemControlState,
        screen_point: ScreenPoint | None,
    ) -> SystemControlState:
        if self._locked_window_ref is None or self._active_window_bounds is None:
            return self._begin_window_action(state, screen_point)
        if screen_point is None or self._window_drag_anchor is None or self._resize_anchor is None:
            state.effect_label = "Waiting for a stable cursor to resize the focused window"
            return state
        if not self.bridge.is_window_size_settable(self._locked_window_ref):
            state.effect_label = (
                f'"{self._locked_window_title or "Focused window"}" cannot be resized through Accessibility'
            )
            self._clear_window_drag_state()
            return state

        delta_x = screen_point[0] - self._window_drag_anchor[0]
        delta_y = screen_point[1] - self._window_drag_anchor[1]
        resized_bounds = self._resized_bounds_from_delta(
            self._active_window_bounds,
            delta_x,
            delta_y,
            self._resize_anchor,
        )
        self.bridge.move_window_to(self._locked_window_ref, (resized_bounds[0], resized_bounds[1]))
        self.bridge.resize_window_to(self._locked_window_ref, (resized_bounds[2], resized_bounds[3]))
        state.target_label = self._locked_window_title
        state.target_locked = self._locked_window_ref is not None
        state.effect_label = (
            f'Resizing "{self._locked_window_title or "Focused window"}" to '
            f'{int(resized_bounds[2])} x {int(resized_bounds[3])}'
        )
        return state

    def _release_active_window(
        self,
        state: SystemControlState,
        screen_point: ScreenPoint | None,
    ) -> SystemControlState:
        target_label = self._locked_window_title
        if (
            self.window_action_mode is WindowActionMode.MOVE
            and self._locked_window_ref is not None
            and screen_point is not None
        ):
            snap_candidate = self._snap_candidate_for_point(screen_point)
            if snap_candidate is not None and self.bridge.is_window_size_settable(self._locked_window_ref):
                snap_label, snap_origin, snap_size = snap_candidate
                self.bridge.move_window_to(self._locked_window_ref, snap_origin)
                self.bridge.resize_window_to(self._locked_window_ref, snap_size)
                self._clear_window_drag_state()
                state.target_label = target_label
                state.target_locked = self._locked_window_ref is not None
                state.effect_label = f'Snapped "{target_label or "Focused window"}" {snap_label}'
                return state

        self._clear_window_drag_state()
        state.target_label = target_label
        state.target_locked = self._locked_window_ref is not None
        if target_label is not None:
            if self.window_action_mode is WindowActionMode.RESIZE:
                state.effect_label = f'Released resize on "{target_label}"'
            else:
                state.effect_label = f'Released "{target_label}"'
        else:
            state.effect_label = "Window mode ready"
        return state

    def _window_idle_label(self, state: SystemControlState) -> str:
        action_label = self.window_action_mode.value
        if state.target_locked and state.target_label is not None:
            return f'Window mode locked to "{state.target_label}" for {action_label}'
        if state.target_label is not None:
            return f'Window mode ready to {action_label} "{state.target_label}"'
        return f"Focus another app window to {action_label} it"

    def _window_ready_label(self, state: SystemControlState) -> str:
        action_label = self.window_action_mode.value
        if state.target_locked and state.target_label is not None:
            return f'Ready to {action_label} locked target "{state.target_label}"'
        if state.target_label is not None:
            return f'Ready to {action_label} "{state.target_label}"'
        return f"Focus another app window to {action_label} it"

    def _resize_anchor_for_point(
        self,
        point: ScreenPoint,
        bounds: WindowBounds,
    ) -> ResizeAnchor:
        center_x = bounds[0] + (bounds[2] / 2.0)
        center_y = bounds[1] + (bounds[3] / 2.0)
        horizontal = "left" if point[0] < center_x else "right"
        vertical = "top" if point[1] < center_y else "bottom"
        return (horizontal, vertical)

    @staticmethod
    def _format_resize_anchor(anchor: ResizeAnchor) -> str:
        return f"{anchor[1]}-{anchor[0]}"

    def _resized_bounds_from_delta(
        self,
        bounds: WindowBounds,
        delta_x: float,
        delta_y: float,
        anchor: ResizeAnchor,
    ) -> WindowBounds:
        origin_x, origin_y, width, height = bounds
        min_width = min(_MIN_WINDOW_WIDTH, width)
        min_height = min(_MIN_WINDOW_HEIGHT, height)
        right = origin_x + width
        bottom = origin_y + height
        horizontal, vertical = anchor

        if horizontal == "left":
            next_origin_x = min(origin_x + delta_x, right - min_width)
            next_width = right - next_origin_x
        else:
            next_origin_x = origin_x
            next_width = max(width + delta_x, min_width)

        if vertical == "top":
            next_origin_y = min(origin_y + delta_y, bottom - min_height)
            next_height = bottom - next_origin_y
        else:
            next_origin_y = origin_y
            next_height = max(height + delta_y, min_height)

        return (
            round(next_origin_x),
            round(next_origin_y),
            round(next_width),
            round(next_height),
        )

    def _snap_candidate_for_point(
        self,
        point: ScreenPoint,
    ) -> tuple[str, ScreenPoint, tuple[float, float]] | None:
        origin_x, origin_y, width, height = self.bridge.main_display_bounds()
        threshold = min(width, height) * _SNAP_THRESHOLD_RATIO
        full_height = round(height)
        full_width = round(width)
        half_width = round(width / 2.0)
        right_width = round(width - half_width)

        if point[1] <= origin_y + threshold:
            return (
                "full screen",
                (round(origin_x), round(origin_y)),
                (full_width, full_height),
            )
        if point[0] <= origin_x + threshold:
            return (
                "left",
                (round(origin_x), round(origin_y)),
                (half_width, full_height),
            )
        if point[0] >= origin_x + width - threshold:
            return (
                "right",
                (round(origin_x + half_width), round(origin_y)),
                (right_width, full_height),
            )
        return None

    def _focused_window_title(self) -> str | None:
        focused_window = self.bridge.copy_focused_window()
        if focused_window is None:
            return None
        try:
            focused_pid = self.bridge.window_pid(focused_window)
            if focused_pid == self._process_pid:
                return None
            return self.bridge.copy_window_title(focused_window) or "Focused window"
        finally:
            self.bridge.release_ref(focused_window)

    def _lock_focused_window_target(self) -> tuple[WindowRef, str, WindowBounds] | str | None:
        focused_window = self.bridge.copy_focused_window()
        if focused_window is None:
            return None

        focused_pid = self.bridge.window_pid(focused_window)
        if focused_pid == self._process_pid:
            self.bridge.release_ref(focused_window)
            return "Focus another app window before locking a target"

        if not self.bridge.is_window_position_settable(focused_window):
            window_title = self.bridge.copy_window_title(focused_window) or "Focused window"
            self.bridge.release_ref(focused_window)
            return f'"{window_title}" cannot be moved through Accessibility'

        window_bounds = self.bridge.copy_window_bounds(focused_window)
        if window_bounds is None:
            self.bridge.release_ref(focused_window)
            return "Could not read the focused window bounds"

        self._clear_window_target()
        self._locked_window_ref = focused_window
        self._locked_window_title = self.bridge.copy_window_title(focused_window) or "Focused window"
        return (self._locked_window_ref, self._locked_window_title, window_bounds)

    def _locked_window_target(self) -> tuple[WindowRef, str, WindowBounds] | None:
        if self._locked_window_ref is None:
            return None

        window_bounds = self.bridge.copy_window_bounds(self._locked_window_ref)
        if window_bounds is None or not self.bridge.is_window_position_settable(self._locked_window_ref):
            self._clear_window_target()
            return None

        return (
            self._locked_window_ref,
            self._locked_window_title or "Focused window",
            window_bounds,
        )

    def _clear_window_drag_state(self) -> None:
        self._active_window_origin = None
        self._active_window_bounds = None
        self._window_drag_anchor = None
        self._resize_anchor = None

    def _clear_window_target(self) -> None:
        self._clear_window_drag_state()
        if self._locked_window_ref is not None:
            self.bridge.release_ref(self._locked_window_ref)
        self._locked_window_ref = None
        self._locked_window_title = None
