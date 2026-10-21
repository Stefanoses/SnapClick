"""Weryfikacja przeplywu przechwytywania: click -> zrzut -> overlay -> zapis.

Symuluje mysz na overlayu i zatwierdzenie nazwy szablonu (atry), bez realnego
zaznaczania na ekranie. Uruchom:  .venv/Scripts/python scripts/verify_capture_flow.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

app = QApplication.instance() or QApplication([])

from snapclick.core.vision.templates import TemplateRegistry  # noqa: E402
from snapclick.gui import templates_panel  # noqa: E402
from snapclick.gui.capture import CaptureDialog  # noqa: E402


class FakeScreen:
    def grab(self, region=None):
        return np.zeros((400, 600, 3), dtype=np.uint8)


class FakeNameDialog:
    """Atra TemplateNameDialog — zawsze zatwierdzona nazwa."""

    def __init__(self, crop, parent=None):
        self._crop = crop

    def exec(self):
        return 1  # QDialog.Accepted

    def template_id(self):
        return "kup_przycisk"


def main() -> int:
    templates_panel.TemplateNameDialog = FakeNameDialog

    registry = TemplateRegistry(Path(tempfile.mkdtemp()))
    parent = QWidget()
    parent.resize(300, 200)
    parent.show()
    app.processEvents()

    dlg = CaptureDialog(FakeScreen(), registry, parent)
    captured = []
    dlg.captured.connect(captured.append)
    dlg.show()
    app.processEvents()

    # 1. klik "Zrob zrzut i zaznacz"
    press = _press(dlg.btn, 20, 18)
    dlg.btn.mousePressEvent(press)
    dlg.btn.mouseReleaseEvent(_release(dlg.btn, 20, 18))
    app.processEvents()

    # 2. czekamy az QTimer(300ms) uruchomi _grab_and_pick
    from PySide6.QtTest import QTest
    QTest.qWait(450)
    app.processEvents()

    overlay = dlg._overlay
    assert overlay is not None, "overlay nie zostal utworzony!"
    assert overlay.isVisible(), "overlay nie jest widoczny!"
    assert not parent.isVisible(), "okno glowne nadal widoczne podczas zrzutu"
    print("OK: overlay pelnoekranowy aktywny, okno glowne schowane")

    # 3. zaznaczenie obszaru (press -> move -> release)
    pt2 = QPointF(150, 140)
    overlay.mousePressEvent(_press_at(QPointF(50, 60)))
    overlay.mouseMoveEvent(_move_at(pt2))
    overlay.mouseReleaseEvent(_release_at(pt2))
    app.processEvents()

    assert not overlay.isVisible(), \
        "nakladka nadal widoczna po zaznaczeniu obszaru!"
    print("OK: nakladka znika natychmiast po zaznaczeniu")

    assert captured == ["kup_przycisk"], f"brak captured: {captured}"
    assert registry.get("kup_przycisk") is not None
    print("OK: szablon zapisany do rejestru, dialog przechwycenia zamkniety")

    # 4. okno glowne przywrócone i responsywne (bez blokady modalnej)
    QTest.qWait(60)
    app.processEvents()
    assert parent.isVisible(), "okno glowne nie zostalo przywrócone!"
    print("OK: okno glowne przywrócone do pracy")

    # 5. sciezka anulowania (Esc)
    dlg2 = CaptureDialog(FakeScreen(), registry, parent)
    dlg2.show()
    app.processEvents()
    dlg2.btn.mousePressEvent(_press(dlg2.btn, 20, 18))
    dlg2.btn.mouseReleaseEvent(_release(dlg2.btn, 20, 18))
    QTest.qWait(450)
    app.processEvents()
    assert dlg2._overlay is not None
    dlg2._on_cancel()
    app.processEvents()
    assert dlg2._overlay is None
    assert parent.isVisible()
    print("OK: Esc/anulowanie przywraca okno bez blokady")

    print("\nCAPTURE FLOW OK")
    return 0


# --------------------------------------------------------------------- pomocnicze
def _press(widget, x, y):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _release(widget, x, y):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def _press_at(p):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseButtonPress, p,
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _move_at(p):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseMove, p, Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def _release_at(p):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseButtonRelease, p,
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


if __name__ == "__main__":
    sys.exit(main())
