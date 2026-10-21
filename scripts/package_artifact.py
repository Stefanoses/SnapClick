"""Package the PyInstaller output into a distributable artifact.

Windows -> ``dist/SnapClick-<ver>-windows.zip`` (contains SnapClick.exe)
Linux   -> ``dist/SnapClick-<ver>-linux.sh``   (self-extracting bundle)

Run directly (after building with PyInstaller):

    python scripts/package_artifact.py

Used by ``scripts/release.py`` and by the GitHub release workflow.
"""
from __future__ import annotations

import base64
import io
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
        "logs) is stored in the 'snapclick-data' folder next to the binary.\n"
        "Copy the whole folder anywhere you like - it stays self-contained.\n\n"
        "Requirements:\n"
        "  * Windows 10/11 - nothing extra\n"
        "  * Linux - an X11 session (not Wayland)\n\n"
        "First run on Windows may trigger SmartScreen ('More info' -> 'Run').\n"
        "The build is unsigned; that is expected for a community release.\n"
    )


def package_windows(version: str) -> Path:
    exe = DIST / f"{APP}.exe"
    if not exe.is_file():
        raise SystemExit(f"missing {exe} - run PyInstaller first")
    out = DIST / f"{APP}-{version}-windows.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe, f"{APP}-{version}/{APP}.exe")
        zf.writestr(f"{APP}-{version}/README.txt", _readme_txt())
        examples = ROOT / "examples"
        if examples.is_dir():
            for f in sorted(examples.rglob("*")):
                if f.is_file():
                    zf.write(f, f"{APP}-{version}/examples/{f.relative_to(examples).as_posix()}")
    return out


def package_linux(version: str) -> Path:
    binary = DIST / APP
    if not binary.is_file():
        raise SystemExit(f"missing {binary} - run PyInstaller first")

    # 1) payload: tar.gz with a versioned folder around the binary
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(binary, arcname=f"{APP}-{version}/{APP}")
        info = tarfile.TarInfo(f"{APP}-{version}/README.txt")
        raw = _readme_txt().encode("utf-8")
        info.size = len(raw)
        tf.addfile(info, io.BytesIO(raw))
    payload = base64.encodebytes(buf.getvalue()).decode("ascii")

    # 2) self-extracting header
    folder = f"{APP}-{version}"
    header = f"""#!/bin/sh
# {APP} {version} - self-extracting bundle for Linux (X11 session required)
#
#   sh {APP}-{version}-linux.sh            extract into the current directory
#   sh {APP}-{version}-linux.sh --run      extract and start immediately
#
set -e
TARGET="$PWD"
RUN=0
for arg in "$@"; do
    case "$arg" in
        --run) RUN=1 ;;
        -h|--help)
            echo "usage: sh $0 [--run]"; exit 0 ;;
    esac
done

echo "Extracting {APP} to $TARGET/{folder} ..."
mkdir -p "$TARGET/{folder}"
tail -n +{LINE_PLACEHOLDER} "$0" | base64 -d | tar xz -C "$TARGET"
chmod +x "$TARGET/{folder}/{APP}"
echo "Done. Start it with: ./{folder}/{APP}"

if [ "$RUN" = "1" ]; then
    exec "$TARGET/{folder}/{APP}"
fi
exit 0
__PAYLOAD_FOLLOWS__
"""
    out = DIST / f"{APP}-{version}-linux.sh"
    # the payload starts on the line right after the marker; compute the
    # concrete line number now that the header text is final
    marker_line = header.count("\n")  # marker is the last header line
    script = header.replace(str(LINE_PLACEHOLDER), str(marker_line + 1))
    out.write_text(script + payload, encoding="utf-8", newline="\n")
    out.chmod(0o755)
    return out


LINE_PLACEHOLDER = "@@FIRST_PAYLOAD_LINE@@"


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
