@echo off
REM Build the standalone Windows bundle (dist\SnapClick.exe).
REM Requires: pip install pyinstaller  (see requirements-build.txt)
setlocal
cd /d "%~dp0.."

python -m PyInstaller packaging\SnapClick.spec --noconfirm
if errorlevel 1 (
  echo BUILD FAILED
  exit /b 1
)

echo.
echo Built: dist\SnapClick.exe
echo Test it: dist\SnapClick.exe
endlocal
