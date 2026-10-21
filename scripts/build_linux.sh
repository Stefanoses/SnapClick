#!/usr/bin/env bash
# Build the standalone Linux bundle (dist/SnapClick).
# Requires: pip install pyinstaller  (see requirements-build.txt)
# Note: build on the oldest distro you want to support (glibc is forward-
# compatible, not backward).
set -euo pipefail
cd "$(dirname "$0")/.."

python -m PyInstaller packaging/SnapClick.spec --noconfirm

echo
echo "Built: dist/SnapClick"
echo "Test it: ./dist/SnapClick"
