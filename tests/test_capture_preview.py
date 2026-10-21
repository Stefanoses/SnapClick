"""Regresja: podglad przechwyconego szablonu musi byc 1:1 z buforem BGR.

Bufor numpy jest upakowany ciasno (bytesPerLine = width * kanaly), a QImage
tworzony bez jawnego bytesPerLine zaokragla szerokosc wiersza do
wielokrotnosci 4 bajtow. Przy szerokosci niepodzielnej przez 4 kazdy
kolejny wiersz byl przesuniety — podglad wygladal na 'sciagniety'
pod katem i rozlazly, choc plik PNG na dysku (osobna sciezka cv2.imwrite)
pozostawal poprawny.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 wymagany")


@pytest.fixture(scope="module")
def qapp_instance():
    from PySide6.QtWidgets import QApplication
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # brak dostepnego QPA (np. CI bez ekranu)
        pytest.skip(f"QApplication niedostepny: {exc}")
    yield app


@pytest.mark.parametrize("width", [67, 64, 143, 131, 1, 2, 3])
def test_bgr_to_qimage_no_row_shear(qapp_instance, width):
    from snapclick.gui.capture import _bgr_to_qimage

    height = 78
    marker = (np.arange(width, dtype=np.int32) * 7 % 251).astype(np.uint8)
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 10                     # B
    arr[:, :, 1] = 200                    # G
    arr[0, :, 2] = marker                 # R tylko w pierwszym wierszu

    img = _bgr_to_qimage(arr)

    assert img.width() == width and img.height() == height
    for x in range(width):
        assert img.pixelColor(x, 0).red() == int(marker[x]), \
            f"shear wierszy w kolumnie {x} (szer. {width})"
        px = img.pixelColor(x, height - 1)
        assert (px.blue(), px.green(), px.red()) == (10, 200, 0)


def test_bgr_to_qimage_rgba_and_gray(qapp_instance):
    """Sciezki 4-kanalowa i gradientowa tez nie moga byc przesuniete."""
    from snapclick.gui.capture import _bgr_to_qimage

    rgba = np.zeros((9, 5, 4), dtype=np.uint8)
    rgba[:, :, 0] = 1                     # B
    rgba[:, :, 1] = 2                     # G
    rgba[:, :, 2] = 3                     # R
    rgba[:, :, 3] = 255                   # A
    img = _bgr_to_qimage(rgba)
    px = img.pixelColor(4, 8)
    assert (px.red(), px.green(), px.blue(), px.alpha()) == (3, 2, 1, 255)

    gray = np.tile(np.arange(7, dtype=np.uint8), (11, 1))
    gimg = _bgr_to_qimage(gray)
    for x in range(7):
        assert gimg.pixelColor(x, 10).red() == x
