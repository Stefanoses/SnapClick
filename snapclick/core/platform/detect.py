"""Automatyczne wykrywanie platformy i dobór backendów.

Windows 11 -> backend Win32 (mss + pydirectinput + ctypes/user32).
Linux     -> wymaga sesji X11 (mss + python-xlib + XTEST).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Mapping, Optional

from ...i18n import t
from .base import (
    BackendError,
    InputBackend,
    PlatformInfo,
    ScreenBackend,
    WindowBackend,
)


def detect_platform(
    sys_module: Optional[object] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> PlatformInfo:
    """Wykrywa OS i typ sesji graficznej. Parametry wstrzykiwalne dla testów."""
    sysm = sys_module if sys_module is not None else sys
    env = environ if environ is not None else os.environ

    platform = str(getattr(sysm, "platform", "")).lower()
    if platform.startswith("win"):
        return PlatformInfo(os_name="windows", session="windows")

    if platform.startswith("linux"):
        display = env.get("DISPLAY") or None
        wayland = env.get("WAYLAND_DISPLAY") or None
        session = (env.get("XDG_SESSION_TYPE") or "").strip().lower()
        if not session:
            if wayland and not display:
                session = "wayland"
            elif display:
                session = "x11"
            elif wayland:
                session = "wayland"
            else:
                session = "none"
        return PlatformInfo(os_name="linux", session=session, display=display)

    return PlatformInfo(os_name="unknown", session="none")


@dataclass(frozen=True)
class BackendBundle:
    """Gotowy zestaw backendów dla wykrytej platformy."""

    platform: PlatformInfo
    screen: ScreenBackend
    input: InputBackend
    windows: WindowBackend

    @property
    def name(self) -> str:
        if self.platform.is_windows:
            return "Windows 11 (Win32)"
        if self.platform.is_linux_x11:
            return "Linux (X11)"
        return f"{self.platform.os_name}/{self.platform.session}"


def create_backends(platform: Optional[PlatformInfo] = None) -> BackendBundle:
    """Tworzy backendy dla bieżącej (lub podanej) platformy."""
    info = platform if platform is not None else detect_platform()

    if info.is_windows:
        from .win32 import Win32InputBackend, Win32WindowBackend
        from ._mss_screen import MssScreenBackend

        return BackendBundle(
            platform=info,
            screen=MssScreenBackend(),
            input=Win32InputBackend(),
            windows=Win32WindowBackend(),
        )

    if info.os_name == "linux":
        if info.session == "wayland":
            raise BackendError(t("detect.wayland"))
        if info.session != "x11":
            raise BackendError(t("detect.no_display"))
        from .x11 import X11InputBackend, X11WindowBackend
        from ._mss_screen import MssScreenBackend

        return BackendBundle(
            platform=info,
            screen=MssScreenBackend(),
            input=X11InputBackend(),
            windows=X11WindowBackend(),
        )

    raise BackendError(t("detect.unsupported",
                         os_name=info.os_name, session=info.session))
