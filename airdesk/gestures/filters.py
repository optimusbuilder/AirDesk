"""Filtering helpers for cursor and gesture smoothing."""

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from airdesk.models.hand import PixelPoint


def ema_point(
    current: PixelPoint,
    previous: PixelPoint | None,
    alpha: float,
) -> PixelPoint:
    """Smooth a point using an exponential moving average."""
    if previous is None:
        return current

    x = round(alpha * current[0] + (1.0 - alpha) * previous[0])
    y = round(alpha * current[1] + (1.0 - alpha) * previous[1])
    return (x, y)


def ema_scalar(current: float, previous: float | None, alpha: float) -> float:
    """Smooth a scalar value using an exponential moving average."""
    if previous is None:
        return current
    return alpha * current + (1.0 - alpha) * previous


class _LowPassFilter:
    """Simple first-order low-pass filter used internally by the 1€ filter."""

    __slots__ = ("_y", "_alpha", "_initialized")

    def __init__(self, alpha: float) -> None:
        self._alpha = min(max(alpha, 0.0), 1.0)
        self._y = 0.0
        self._initialized = False

    def apply(self, value: float, alpha: float | None = None) -> float:
        if alpha is not None:
            self._alpha = min(max(alpha, 0.0), 1.0)
        if not self._initialized:
            self._y = value
            self._initialized = True
        else:
            self._y = self._alpha * value + (1.0 - self._alpha) * self._y
        return self._y

    def reset(self) -> None:
        self._initialized = False
        self._y = 0.0


@dataclass(slots=True)
class OneEuroFilter:
    """Adaptive low-pass filter for 2D cursor positions.

    The 1€ (One Euro) filter adapts its cutoff frequency based on the speed
    of the input signal. When the signal moves slowly, the filter smooths
    aggressively to remove jitter. When the signal moves quickly, the filter
    responds immediately to avoid lag.

    Reference: Casiez, Roussel, Vogel — CHI 2012.
    """

    min_cutoff: float = 1.0
    beta: float = 0.007
    d_cutoff: float = 1.0
    time_fn: Callable[[], float] = field(default=time.monotonic)

    _x_filter: _LowPassFilter = field(default_factory=lambda: _LowPassFilter(1.0), init=False)
    _y_filter: _LowPassFilter = field(default_factory=lambda: _LowPassFilter(1.0), init=False)
    _dx_filter: _LowPassFilter = field(default_factory=lambda: _LowPassFilter(1.0), init=False)
    _dy_filter: _LowPassFilter = field(default_factory=lambda: _LowPassFilter(1.0), init=False)
    _last_time: float | None = field(default=None, init=False)
    _initialized: bool = field(default=False, init=False)

    def apply(self, point: PixelPoint) -> PixelPoint:
        """Filter a raw pixel point and return the smoothed result."""
        now = self.time_fn()
        x = float(point[0])
        y = float(point[1])

        if not self._initialized or self._last_time is None:
            self._x_filter.reset()
            self._y_filter.reset()
            self._dx_filter.reset()
            self._dy_filter.reset()
            self._x_filter.apply(x)
            self._y_filter.apply(y)
            self._dx_filter.apply(0.0)
            self._dy_filter.apply(0.0)
            self._last_time = now
            self._initialized = True
            return point

        dt = now - self._last_time
        if dt <= 0.0:
            dt = 1.0 / 30.0  # Assume ~30 FPS as fallback
        self._last_time = now

        rate = 1.0 / dt

        # Estimate the derivative (speed) for each axis.
        dx = (x - self._x_filter._y) * rate
        dy = (y - self._y_filter._y) * rate

        # Low-pass filter the derivative.
        d_alpha = self._smoothing_factor(rate, self.d_cutoff)
        edx = self._dx_filter.apply(dx, d_alpha)
        edy = self._dy_filter.apply(dy, d_alpha)

        # Adapt the cutoff frequency based on the speed.
        speed = math.hypot(edx, edy)
        cutoff = self.min_cutoff + self.beta * speed

        # Low-pass filter the signal with the adapted cutoff.
        alpha = self._smoothing_factor(rate, cutoff)
        fx = self._x_filter.apply(x, alpha)
        fy = self._y_filter.apply(y, alpha)

        return (round(fx), round(fy))

    def reset(self) -> None:
        """Clear all internal state so the next call starts fresh."""
        self._x_filter.reset()
        self._y_filter.reset()
        self._dx_filter.reset()
        self._dy_filter.reset()
        self._last_time = None
        self._initialized = False

    @staticmethod
    def _smoothing_factor(rate: float, cutoff: float) -> float:
        """Compute the exponential smoothing factor for a given frame rate and cutoff."""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau * rate)
