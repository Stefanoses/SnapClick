"""Testy autodetekcji platformy (wstrzykiwalne sys/os.environ)."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from snapclick.core.platform.base import BackendError
from snapclick.core.platform.detect import create_backends, detect_platform


def test_windows_detected():
    info = detect_platform(SimpleNamespace(platform="win32"), {})
    assert info.os_name == "windows"
    assert info.is_windows
    assert not info.is_linux_x11


def test_linux_x11_detected_via_env():
    info = detect_platform(
        SimpleNamespace(platform="linux"),
        {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"},
    )
    assert info.is_linux_x11


def test_linux_wayland_detected():
    info = detect_platform(
        SimpleNamespace(platform="linux"),
        {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"},
    )
    assert info.session == "wayland"
    with pytest.raises(BackendError, match="Wayland"):
        create_backends(info)


def test_linux_no_display():
    info = detect_platform(SimpleNamespace(platform="linux"), {})
    assert info.session == "none"
    with pytest.raises(BackendError, match="DISPLAY"):
        create_backends(info)


def test_unknown_os():
    info = detect_platform(SimpleNamespace(platform="darwin"), {})
    assert info.os_name == "unknown"
    with pytest.raises(BackendError):
        create_backends(info)


@pytest.mark.skipif(sys.platform != "win32",
                    reason="backend Win32 (ctypes.wintypes) tylko na Windows")
def test_windows_backend_bundle_created():
    """Na Windows bundle: mss + input przez SendInput (wymaga pydirectinput)."""
    info = detect_platform(SimpleNamespace(platform="win32"), {})
    try:
        bundle = create_backends(info)
    except BackendError:  # środowisko CI bez pydirectinput
        pytest.skip("pydirectinput niedostępny")
    assert bundle.screen.name == "mss"
    assert "sendinput" in bundle.input.name
    assert bundle.name == "Windows 11 (Win32)"
