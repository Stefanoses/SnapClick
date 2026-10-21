"""Package the PyInstaller output into distributable artifacts.

Windows -> ``dist/SnapClick-<ver>-windows.zip``   (contains SnapClick.exe)
Linux   -> ``dist/SnapClick-<ver>-linux.tar.gz``  (folder with the binary)
           ``dist/SnapClick-<ver>-x86_64.AppImage`` is built separately by
           ``scripts/build_appimage.sh`` (needs appimagetool).

Run directly (after building with PyInstaller):

    python scripts/package_artifact.py

Used by ``scripts/release.py`` and by the GitHub release workflow.
"""
from __future__ import annotations

import os
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snapclick.version import __version__  # noqa: E402

DIST = ROOT / "dist"
APP = "SnapClick"


def _readme_txt() -> str:
    return (
        f"{APP} {__version__}\n"
        "---------------------\n\n"
        "Portable build: everything the app writes (settings, projects,\n"
        "logs) is stored in the 'snapclick-data' folder next to the binary\n"
        "(or next to the .AppImage file). Copy it anywhere you like - it\n"
        "stays self-contained.\n\n"
        "Requirements:\n"
        "  * Windows 10/11 - nothing extra\n"
        "  * Linux - an X11 session (not Wayland)\n\n"
        "First run on Windows may trigger SmartScreen ('More info' -> 'Run').\n"
        "The build is unsigned; that is expected for a community release.\n\n"
        "Linux quick start (tar.gz):\n"
        "  tar xzf SnapClick-*-linux.tar.gz\n"
        "  cd SnapClick-*/\n"
        "  ./SnapClick\n"
    )


def _add_examples(zf_or_none) -> None:
    pass


def package_windows(version: str) -> Path:
    exe = DIST / f"{APP}.exe"
    if not exe.is_file():
        raise SystemExit(f"missing {exe} - run PyInstaller first")
    out = DIST / f"{APP}-{version}-windows.zip"
    folder = f"{APP}-{version}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe, f"{folder}/{APP}.exe")
        zf.writestr(f"{folder}/README.txt", _readme_txt())
        _zip_examples(zf, folder)
    return out


def _zip_examples(zf: zipfile.ZipFile, folder: str) -> None:
    examples = ROOT / "examples"
    if examples.is_dir():
        for f in sorted(examples.rglob("*")):
            if f.is_file():
                zf.write(f, f"{folder}/examples/"
                         f"{f.relative_to(examples).as_posix()}")


def package_linux(version: str) -> Path:
    binary = DIST / APP
    if not binary.is_file():
        raise SystemExit(f"missing {binary} - run PyInstaller first")
    out = DIST / f"{APP}-{version}-linux.tar.gz"
    folder = f"{APP}-{version}"
    with tarfile.open(out, "w:gz") as tf:
        # preserve the executable bit
        tf.add(binary, arcname=f"{folder}/{APP}")
        _add_bytes(tf, f"{folder}/README.txt", _readme_txt())
        examples = ROOT / "examples"
        if examples.is_dir():
            for f in sorted(examples.rglob("*")):
                if f.is_file():
                    tf.add(f, arcname=f"{folder}/examples/"
                                    f"{f.relative_to(examples).as_posix()}")
    return out


def _add_bytes(tf: tarfile.TarFile, name: str, text: str) -> None:
    import io
    raw = text.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(raw)
    info.mode = 0o644
    tf.addfile(info, io.BytesIO(raw))


def main() -> int:
    version = __version__
    if sys.platform == "win32":
        out = package_windows(version)
    else:
        out = package_linux(version)
    print(f"Artifact: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
