#!/usr/bin/env bash
# Build SnapClick-<version>-x86_64.AppImage from the PyInstaller output.
#
# Requires (CI installs them):
#   - dist/SnapClick           (scripts/build_linux.sh)
#   - packaging/snapclick.png  (python scripts/make_icon.py)
#   - appimagetool on PATH or at ./appimagetool (downloaded by CI)
#
# Usage: bash scripts/build_appimage.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(python - <<'EOF'
import re, pathlib
m = re.search(r'__version__ = "([^"]+)"',
              pathlib.Path("snapclick/version.py").read_text(encoding="utf-8"))
print(m.group(1))
EOF
)"

BIN=dist/SnapClick
ICON=packaging/snapclick.png
[ -f "$BIN" ] || { echo "missing $BIN - run scripts/build_linux.sh first"; exit 1; }
[ -f "$ICON" ] || { echo "missing $ICON - run python scripts/make_icon.py"; exit 1; }

TOOL="${APPIMAGETOOL:-./appimagetool}"
[ -x "$TOOL" ] || { echo "appimagetool not found (set APPIMAGETOOL=...)"; exit 1; }

APPDIR=build/SnapClick.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

cp "$BIN" "$APPDIR/usr/bin/snapclick"
chmod +x "$APPDIR/usr/bin/snapclick"
cp "$ICON" "$APPDIR/snapclick.png"
cp "$ICON" "$APPDIR/.DirIcon"

cat > "$APPDIR/snapclick.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SnapClick
Comment=Visual vision-based automation editor
Exec=snapclick %F
Icon=snapclick
Categories=Utility;
Terminal=false
EOF

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
# Inside an AppImage the real .AppImage path is in $APPIMAGE; snapclick/
# paths.py uses it to keep snapclick-data/ next to the file (portable).
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/snapclick" "$@"
EOF
chmod +x "$APPDIR/AppRun"

OUT="dist/SnapClick-${VERSION}-x86_64.AppImage"
# appimagetool is itself an AppImage; runners without FUSE need the
# extract-and-run mode via env var.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$TOOL" "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "Built: $OUT"
