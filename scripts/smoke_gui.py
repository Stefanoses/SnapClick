"""Ręczny smoke-test GUI: otwiera okno, ładuje przykład, renderuje, zamyka.

    .venv/Scripts/python scripts/smoke_gui.py

Okno pojawia się na ~2 s (widenie renderu) i zamyka sie automatycznie.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from snapclick.gui.app import _enable_windows_dpi
from snapclick.gui.main_window import MainWindow


def main() -> int:
    _enable_windows_dpi()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    step = {"n": 0}

    def tick() -> None:
        step["n"] += 1
        if step["n"] == 1:
            example = ROOT / "examples" / "demo_click_loop.snapclick"
            if example.is_file():
                win.storage.load(example)
                win._attach_storage()
                win._log("Przyklad wczytany (smoke).")
        elif step["n"] == 3:
            problems = win.storage.program.validate()
            win._log(f"Walidacja po ladowaniu: "
                     f"{'OK' if not problems else problems}")
            win.storage.dirty = False
            win.close()
            app.quit()

    timer = QTimer()
    timer.setInterval(600)
    timer.timeout.connect(tick)
    timer.start()
    code = app.exec()
    print("SMOKE OK" if code == 0 else f"SMOKE exit={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
