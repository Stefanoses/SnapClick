"""Uruchomienie aplikacji GUI (punkt wejscia ``python main.py``).

Na Windows ustawiamy DPI-awareness (Win32 API) — wspolrzedne myszy i zrzutow
musza byc w pikselach fizycznych; manifest robimy wywolaniem ctypes przed
utworzeniem QApplication.

Dodatkowo wlaczamy faulthandler + globalny excepthook: awarie natywne
(np. fast-fail 0xC0000409) nie generuja pythonowego tracebacka, wiec zrzut
stosu C trafia do pliku logs/crash.log — bez niego pozostaje tylko kod
wyjscia procesu.
"""
from __future__ import annotations

import sys


def _enable_windows_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # PROCESS_PER_MONITOR_DPI_AWARE_V2 = 2
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass  # środowiska bez shcore — Qt i tak da rade, tylko mniej ostro


def _install_crash_diagnostics() -> None:
    """Zrzut natywnego stosu przy SegFault/fast-fail + log wyjatkow Pythona.

    Bez tego proces wysypujacy sie w warstwie C++ (Qt/Shiboken) konczy sie
    kodym 0xC0000409/0xC0000005 i ZADNYM sladem w stdout.
    """
    import faulthandler

    from ..core.paths import logs_dir

    log_dir = logs_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        crash_fp = (log_dir / "crash.log").open("a", encoding="utf-8")
    except OSError:
        crash_fp = sys.stderr  # fallback — tylko stderr
    faulthandler.enable(file=crash_fp, all_threads=True)

    def _hook(exc_type, exc, tb):
        # 1) standardowy traceback do stderr
        sys.__excepthook__(exc_type, exc, tb)
        # 2) ten sam traceback do crash.log (aplikacja GUI nie ma konsoli)
        import traceback
        try:
            with (log_dir / "crash.log").open("a", encoding="utf-8") as fp:
                traceback.print_exception(exc_type, exc, tb, file=fp)
        except OSError:
            pass

    if crash_fp is not sys.stderr:
        sys.excepthook = _hook


def main() -> int:
    _enable_windows_dpi()
    _install_crash_diagnostics()
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    from .theme import STYLE

    app = QApplication(sys.argv)
    app.setApplicationName("SnapClick")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
