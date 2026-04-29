"""Transparent overlay window for macOS via ctypes + Objective-C runtime.

This module creates a borderless, transparent, always-on-top, click-through
window that renders the AirDesk trackpad zone, cursor, and status pill
directly on the user's desktop — no camera preview window needed.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import math
from typing import Any

from airdesk.system.intents import PointerPhase, SystemControlState


# ============================================================
# Objective-C Runtime Helpers
# ============================================================

_objc = ctypes.CDLL(ctypes.util.find_library("objc"))
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]

# AppKit is loaded lazily when OverlayWindow is created to avoid
# conflicts with MediaPipe's Metal/GL context initialization.
_appkit_loaded = False


def _ensure_appkit() -> None:
    global _appkit_loaded
    if not _appkit_loaded:
        ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        _appkit_loaded = True


def _cls(name: str) -> int:
    """Get an ObjC class by name."""
    return _objc.objc_getClass(name.encode())


def _sel(name: str) -> int:
    """Register and return an ObjC selector."""
    return _objc.sel_registerName(name.encode())


def _msg(obj, sel_name: str, *args, restype=ctypes.c_void_p, argtypes=None):
    """Send an ObjC message with explicit typing."""
    sel = _sel(sel_name)
    _objc.objc_msgSend.restype = restype
    _objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + (
        argtypes or []
    )
    return _objc.objc_msgSend(obj, sel, *args)


# ============================================================
# AppKit / CoreGraphics Constants
# ============================================================

_NS_BORDERLESS_WINDOW_MASK = 0
_NS_BACKING_STORE_BUFFERED = 2
_NS_ACTIVATION_POLICY_ACCESSORY = 1
_NS_FLOATING_WINDOW_LEVEL = 3
# NSWindowCollectionBehaviorCanJoinAllSpaces | Stationary
_NS_COLLECTION_BEHAVIOR = (1 << 0) | (1 << 4)

_K_CGIMAGE_ALPHA_PREMULTIPLIED_LAST = 1  # RGBA premultiplied
_K_CG_BITMAP_BYTE_ORDER_32_BIG = 1 << 12


# ============================================================
# Struct types
# ============================================================


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


# ============================================================
# Core drawing helpers (pure numpy — no OpenCV dependency)
# ============================================================

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def _draw_rect_alpha(
    buf: Any,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    r: int,
    g: int,
    b: int,
    a: int,
) -> None:
    """Draw a filled rectangle with alpha blending into an RGBA buffer."""
    h, w = buf.shape[:2]
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w), min(y2, h)
    if x2 <= x1 or y2 <= y1:
        return
    alpha = a / 255.0
    region = buf[y1:y2, x1:x2]
    region[:, :, 0] = np.clip(region[:, :, 0] * (1 - alpha) + r * alpha, 0, 255).astype(
        np.uint8
    )
    region[:, :, 1] = np.clip(region[:, :, 1] * (1 - alpha) + g * alpha, 0, 255).astype(
        np.uint8
    )
    region[:, :, 2] = np.clip(region[:, :, 2] * (1 - alpha) + b * alpha, 0, 255).astype(
        np.uint8
    )
    region[:, :, 3] = np.clip(region[:, :, 3] + a * alpha, 0, 255).astype(np.uint8)


def _draw_rect_border(
    buf: Any,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    r: int,
    g: int,
    b: int,
    a: int,
    thickness: int = 2,
) -> None:
    """Draw a rectangle border."""
    _draw_rect_alpha(buf, x1, y1, x2, y1 + thickness, r, g, b, a)  # top
    _draw_rect_alpha(buf, x1, y2 - thickness, x2, y2, r, g, b, a)  # bottom
    _draw_rect_alpha(buf, x1, y1, x1 + thickness, y2, r, g, b, a)  # left
    _draw_rect_alpha(buf, x2 - thickness, y1, x2, y2, r, g, b, a)  # right


def _draw_circle(
    buf: Any,
    cx: int,
    cy: int,
    radius: int,
    r: int,
    g: int,
    b: int,
    a: int,
    filled: bool = True,
    thickness: int = 2,
) -> None:
    """Draw a circle into the RGBA buffer."""
    h, w = buf.shape[:2]
    y_min = max(cy - radius - thickness, 0)
    y_max = min(cy + radius + thickness + 1, h)
    x_min = max(cx - radius - thickness, 0)
    x_max = min(cx + radius + thickness + 1, w)

    yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
    dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2

    if filled:
        mask = dist_sq <= radius * radius
    else:
        outer = radius + thickness / 2
        inner = radius - thickness / 2
        mask = (dist_sq <= outer * outer) & (dist_sq >= inner * inner)

    alpha = a / 255.0
    region = buf[y_min:y_max, x_min:x_max]
    region[mask, 0] = np.clip(region[mask, 0] * (1 - alpha) + r * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 1] = np.clip(region[mask, 1] * (1 - alpha) + g * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 2] = np.clip(region[mask, 2] * (1 - alpha) + b * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 3] = np.clip(region[mask, 3] + a * alpha, 0, 255).astype(np.uint8)


def _draw_arc(
    buf: Any,
    cx: int,
    cy: int,
    radius: int,
    start_deg: float,
    end_deg: float,
    r: int,
    g: int,
    b: int,
    a: int,
    thickness: int = 3,
) -> None:
    """Draw an arc (partial circle outline)."""
    h, w = buf.shape[:2]
    y_min = max(cy - radius - thickness, 0)
    y_max = min(cy + radius + thickness + 1, h)
    x_min = max(cx - radius - thickness, 0)
    x_max = min(cx + radius + thickness + 1, w)

    yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
    dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
    outer = radius + thickness / 2
    inner = radius - thickness / 2
    ring_mask = (dist_sq <= outer * outer) & (dist_sq >= inner * inner)

    angles = np.degrees(np.arctan2(-(yy - cy), xx - cx)) % 360
    start_deg = start_deg % 360
    end_deg = end_deg % 360
    if start_deg <= end_deg:
        angle_mask = (angles >= start_deg) & (angles <= end_deg)
    else:
        angle_mask = (angles >= start_deg) | (angles <= end_deg)

    mask = ring_mask & angle_mask
    alpha = a / 255.0
    region = buf[y_min:y_max, x_min:x_max]
    region[mask, 0] = np.clip(region[mask, 0] * (1 - alpha) + r * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 1] = np.clip(region[mask, 1] * (1 - alpha) + g * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 2] = np.clip(region[mask, 2] * (1 - alpha) + b * alpha, 0, 255).astype(
        np.uint8
    )
    region[mask, 3] = np.clip(region[mask, 3] + a * alpha, 0, 255).astype(np.uint8)


# ============================================================
# Overlay Window
# ============================================================


class OverlayWindow:
    """Transparent, click-through overlay window for AirDesk.

    Draws the virtual trackpad zone, cursor dot, dwell ring, and a
    status pill directly on the desktop.  The window is invisible to
    mouse events so the real system pointer passes right through it.
    """

    # Trackpad visual config (screen pixels)
    TRACKPAD_WIDTH = 420
    TRACKPAD_HEIGHT = 280
    CURSOR_RADIUS = 12
    PILL_HEIGHT = 36
    PILL_WIDTH = 260
    PILL_Y_OFFSET = 40

    def __init__(self, screen_width: int, screen_height: int) -> None:
        if np is None:
            raise RuntimeError("numpy is required for the overlay window")
        _ensure_appkit()
        self._screen_w = screen_width
        self._screen_h = screen_height
        self._window: int | None = None
        self._image_view: int | None = None
        self._ns_image: int | None = None

        # CoreGraphics lib for CGImage creation
        cg_path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        self._cg = ctypes.CDLL(cg_path)
        self._configure_cg()

        self._init_app()
        self._create_window()

    # ----------------------------------------------------------
    # CoreGraphics signatures
    # ----------------------------------------------------------

    def _configure_cg(self) -> None:
        cg = self._cg
        cg.CGColorSpaceCreateDeviceRGB.restype = ctypes.c_void_p
        cg.CGColorSpaceCreateDeviceRGB.argtypes = []
        cg.CGDataProviderCreateWithData.restype = ctypes.c_void_p
        cg.CGDataProviderCreateWithData.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
        ]
        cg.CGImageCreate.restype = ctypes.c_void_p
        cg.CGImageCreate.argtypes = [
            ctypes.c_size_t,  # width
            ctypes.c_size_t,  # height
            ctypes.c_size_t,  # bitsPerComponent
            ctypes.c_size_t,  # bitsPerPixel
            ctypes.c_size_t,  # bytesPerRow
            ctypes.c_void_p,  # colorSpace
            ctypes.c_uint32,  # bitmapInfo
            ctypes.c_void_p,  # dataProvider
            ctypes.c_void_p,  # decode
            ctypes.c_bool,  # shouldInterpolate
            ctypes.c_int,  # renderingIntent
        ]
        cg.CGImageRelease.restype = None
        cg.CGImageRelease.argtypes = [ctypes.c_void_p]
        cg.CGColorSpaceRelease.restype = None
        cg.CGColorSpaceRelease.argtypes = [ctypes.c_void_p]
        cg.CGDataProviderRelease.restype = None
        cg.CGDataProviderRelease.argtypes = [ctypes.c_void_p]

    # ----------------------------------------------------------
    # NSApplication + NSWindow setup
    # ----------------------------------------------------------

    def _init_app(self) -> None:
        app = _msg(_cls("NSApplication"), "sharedApplication")
        _msg(
            app,
            "setActivationPolicy:",
            ctypes.c_int64(_NS_ACTIVATION_POLICY_ACCESSORY),
            argtypes=[ctypes.c_int64],
        )

    def _create_window(self) -> None:
        rect = _CGRect(
            _CGPoint(0, 0),
            _CGSize(self._screen_w, self._screen_h),
        )

        alloc = _msg(_cls("NSWindow"), "alloc")
        self._window = _msg(
            alloc,
            "initWithContentRect:styleMask:backing:defer:",
            rect,
            ctypes.c_uint64(_NS_BORDERLESS_WINDOW_MASK),
            ctypes.c_uint64(_NS_BACKING_STORE_BUFFERED),
            ctypes.c_bool(False),
            argtypes=[_CGRect, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_bool],
        )

        _msg(self._window, "setOpaque:", ctypes.c_bool(False), argtypes=[ctypes.c_bool])

        clear = _msg(_cls("NSColor"), "clearColor")
        _msg(self._window, "setBackgroundColor:", clear, argtypes=[ctypes.c_void_p])

        _msg(
            self._window,
            "setLevel:",
            ctypes.c_int64(_NS_FLOATING_WINDOW_LEVEL),
            argtypes=[ctypes.c_int64],
        )

        _msg(
            self._window,
            "setIgnoresMouseEvents:",
            ctypes.c_bool(True),
            argtypes=[ctypes.c_bool],
        )

        _msg(
            self._window,
            "setCollectionBehavior:",
            ctypes.c_uint64(_NS_COLLECTION_BEHAVIOR),
            argtypes=[ctypes.c_uint64],
        )

        self._image_view = _msg(
            _msg(_cls("NSImageView"), "alloc"),
            "initWithFrame:",
            rect,
            argtypes=[_CGRect],
        )
        _msg(
            self._window,
            "setContentView:",
            self._image_view,
            argtypes=[ctypes.c_void_p],
        )

        _msg(self._window, "orderFrontRegardless")

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def update(self, system_state: SystemControlState) -> None:
        """Redraw the overlay for the current frame."""
        buf = np.zeros((self._screen_h, self._screen_w, 4), dtype=np.uint8)

        tp_x, tp_y, tp_w, tp_h = self._screen_trackpad_rect()
        is_engaged = system_state.clutch_engaged

        # --- Trackpad zone ---
        if is_engaged:
            _draw_rect_alpha(
                buf, tp_x, tp_y, tp_x + tp_w, tp_y + tp_h, 100, 200, 255, 50
            )
            _draw_rect_border(
                buf, tp_x, tp_y, tp_x + tp_w, tp_y + tp_h, 100, 200, 255, 180, 2
            )
        else:
            _draw_rect_alpha(
                buf, tp_x, tp_y, tp_x + tp_w, tp_y + tp_h, 180, 180, 180, 35
            )
            _draw_rect_border(
                buf, tp_x, tp_y, tp_x + tp_w, tp_y + tp_h, 180, 180, 180, 100, 1
            )

        # --- Cursor dot ---
        if system_state.normalized_cursor is not None and is_engaged:
            nx, ny = system_state.normalized_cursor
            cx = int(tp_x + nx * tp_w)
            cy = int(tp_y + ny * tp_h)

            # Outer ring
            _draw_circle(buf, cx, cy, self.CURSOR_RADIUS, 255, 255, 255, 220, False, 2)
            # Inner dot
            _draw_circle(buf, cx, cy, 4, 255, 255, 255, 255, True)

            # Dwell progress ring
            if system_state.dwell_progress > 0:
                progress = system_state.dwell_progress
                start = 90  # top
                sweep = progress * 360
                end = (start - sweep) % 360
                color_r = 100 if progress < 0.44 else 255
                color_g = 220 if progress < 0.44 else 220
                color_b = 100 if progress < 0.44 else 0
                _draw_arc(
                    buf,
                    cx,
                    cy,
                    self.CURSOR_RADIUS + 8,
                    end,
                    start,
                    color_r,
                    color_g,
                    color_b,
                    220,
                    3,
                )

        # --- Status pill ---
        pill_x = (self._screen_w - self.PILL_WIDTH) // 2
        pill_y = self.PILL_Y_OFFSET
        _draw_rect_alpha(
            buf,
            pill_x,
            pill_y,
            pill_x + self.PILL_WIDTH,
            pill_y + self.PILL_HEIGHT,
            30,
            30,
            30,
            200,
        )
        _draw_rect_border(
            buf,
            pill_x,
            pill_y,
            pill_x + self.PILL_WIDTH,
            pill_y + self.PILL_HEIGHT,
            80,
            80,
            80,
            180,
            1,
        )

        self._blit(buf)

    def close(self) -> None:
        """Tear down the overlay window."""
        if self._window is not None:
            _msg(self._window, "close")
            self._window = None

    # ----------------------------------------------------------
    # Internal rendering
    # ----------------------------------------------------------

    def _screen_trackpad_rect(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) of the trackpad in screen coords."""
        x = (self._screen_w - self.TRACKPAD_WIDTH) // 2
        y = (self._screen_h - self.TRACKPAD_HEIGHT) // 2 + 80  # slightly below center
        return x, y, self.TRACKPAD_WIDTH, self.TRACKPAD_HEIGHT

    def _blit(self, rgba_buf: Any) -> None:
        """Push an RGBA numpy buffer to the overlay window."""
        h, w = rgba_buf.shape[:2]
        data = rgba_buf.tobytes()

        color_space = self._cg.CGColorSpaceCreateDeviceRGB()
        provider = self._cg.CGDataProviderCreateWithData(
            None,
            data,
            len(data),
            None,
        )

        bitmap_info = _K_CGIMAGE_ALPHA_PREMULTIPLIED_LAST | _K_CG_BITMAP_BYTE_ORDER_32_BIG
        cg_image = self._cg.CGImageCreate(
            w,
            h,
            8,
            32,
            w * 4,
            color_space,
            bitmap_info,
            provider,
            None,
            False,
            0,
        )

        # Wrap CGImage in NSImage
        ns_size = _CGSize(w, h)
        ns_image = _msg(_msg(_cls("NSImage"), "alloc"), "initWithSize:", ns_size, argtypes=[_CGSize])
        ns_bitmapimagerep = _msg(
            _msg(_cls("NSBitmapImageRep"), "alloc"),
            "initWithCGImage:",
            ctypes.c_void_p(cg_image),
            argtypes=[ctypes.c_void_p],
        )
        _msg(ns_image, "addRepresentation:", ns_bitmapimagerep, argtypes=[ctypes.c_void_p])

        # Set on image view
        _msg(self._image_view, "setImage:", ns_image, argtypes=[ctypes.c_void_p])

        # Release previous NSImage if any
        if self._ns_image is not None:
            _msg(self._ns_image, "release", restype=None)
        self._ns_image = ns_image

        # Release CoreGraphics objects
        _msg(ns_bitmapimagerep, "release", restype=None)
        self._cg.CGImageRelease(cg_image)
        self._cg.CGDataProviderRelease(provider)
        self._cg.CGColorSpaceRelease(color_space)
