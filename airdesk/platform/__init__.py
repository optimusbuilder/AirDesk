"""Platform backends for AirDesk system control."""

from airdesk.platform.base import SystemBackend
from airdesk.platform.macos import MacOSSystemBackend
from airdesk.platform.shadow import ShadowSystemBackend

__all__ = [
    "MacOSSystemBackend",
    "ShadowSystemBackend",
    "SystemBackend",
]
