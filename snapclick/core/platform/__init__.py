"""Abstrakcja i implementacje warstwy platformowej (Windows 11 / Linux X11)."""

from .base import (
    BackendError,
    InputBackend,
    PlatformInfo,
    Region,
    ScreenBackend,
    WindowBackend,
    WindowInfo,
)
from .detect import BackendBundle, create_backends, detect_platform

__all__ = [
    "BackendError",
    "BackendBundle",
    "InputBackend",
    "PlatformInfo",
    "Region",
    "ScreenBackend",
    "WindowBackend",
    "WindowInfo",
    "create_backends",
    "detect_platform",
]
