"""One-command release: bump version -> commit -> tag -> push -> build.

Usage (from the repo root):

    python scripts/release.py 1.1.0

What it does:
  1. writes the new version into ``snapclick/version.py``
  2. runs the test suite (aborts on failure)
  3. commits the bump and creates an annotated tag ``v<version>``
  4. pushes ``main`` and the tag to ``origin``
  5. builds the standalone bundle for the current OS
     (``scripts/build_windows.bat`` / ``scripts/build_linux.sh``)
     and packages it into ``dist/`` (zip on Windows, .sh on Linux)

The GitHub release itself is created by the CI workflow
(``.github/workflows/release.yml``) when the tag lands on GitHub: it
builds Windows + Linux artifacts and attaches them to the release.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "snapclick" / "version.py"
PATTERN = re.compile(r'__version__ = "([^"]+)"')


def run(*cmd: str, check: bool = True) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    code = proc.returncode
    if check and code != 0:
        sys.exit(f"command failed ({code}): {' '.join(cmd)}")
    return code


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: python scripts/release.py <major.minor.patch>")
    version = sys.argv[1]

    text = VERSION_FILE.read_text(encoding="utf-8")
    if PATTERN.search(text) is None:
        sys.exit("version.py malformed — expected __version__ = \"x.y.z\"")
    VERSION_FILE.write_text(PATTERN.sub(f'__version__ = "{version}"', text),
                            encoding="utf-8")
    print(f"version -> {version}")

    run(sys.executable, "-m", "pytest", "tests", "-q")

    run("git", "add", "-A")
    run("git", "commit", "-m", f"release: v{version}", check=False)
    run("git", "tag", "-a", f"v{version}", "-m", f"SnapClick v{version}")
    run("git", "push", "origin", "main")
    run("git", "push", "origin", f"v{version}")

    # local build (optional convenience; CI builds the official artifacts)
    if sys.platform == "win32":
        run("cmd", "/c", "scripts\\build_windows.bat", check=False)
        run(sys.executable, "scripts/package_artifact.py", check=False)
    else:
        run("bash", "scripts/build_linux.sh", check=False)
        run(sys.executable, "scripts/package_artifact.py", check=False)

    print(f"\nReleased v{version}. GitHub Actions will publish the release "
          f"artifacts once the tag is pushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
