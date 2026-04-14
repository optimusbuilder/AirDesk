"""Filtering helpers for cursor and gesture smoothing."""

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
