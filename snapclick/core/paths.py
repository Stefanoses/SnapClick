"""Portable data locations: everything lives next to the app.

SnapClick is shipped as a standalone build (PyInstaller). To keep a
downloaded copy fully self-contained, settings, projects and logs are
stored in a ``snapclick-data/`` folder right next to the executable (or
next to the repo root when running from source).

A one-time migration copies settings from the legacy per-user locations
(``%APPDATA%/M2AutoVision`` / ``~/.config/m2autovision``) so existing
users keep their preferences after upgrading.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DATA_DIRNAME = "snapclick-data"


def app_dir() -> Path:
    """Directory of the executable (frozen) or of the repository root."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return app_dir() / DATA_DIRNAME


def settings_file() -> Path:
    """Path to ``settings.json`` (migrates the legacy file on first use)."""
    target = data_dir() / "settings.json"
    if not target.exists():
        for legacy in _legacy_settings_candidates():
            if legacy.is_file():
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(legacy, target)
                except OSError:
                    pass
                break
    return target


def projects_dir() -> Path:
    return data_dir() / "projects"


def logs_dir() -> Path:
    return data_dir() / "logs"


def _legacy_settings_candidates() -> list[Path]:
    out: list[Path] = []
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        out.append(Path(base) / "M2AutoVision" / "settings.json")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        out.append(Path(base) / "m2autovision" / "settings.json")
    return out
