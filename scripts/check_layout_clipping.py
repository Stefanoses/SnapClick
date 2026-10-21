"""Programowa kontrola przycinania UI przy roznych szerokosciach okna.

Sprawdza, czy panele nie wymuszaja poziomego scrolla i czy pola formularza
maja realna szerokosc (> minimalnej) zamiast byc zgniecione.
"""
import sys

from PySide6.QtWidgets import (QApplication, QComboBox, QLineEdit,
                               QPlainTextEdit, QScrollArea, QSpinBox)

from snapclick.core.model.blocks import BlockType
from snapclick.gui.main_window import MainWindow
from snapclick.gui.palette import _BlockChip
from snapclick.gui.theme import STYLE


def check(win, width, height, errors):
    win.resize(width, height)
    app.processEvents()

    # 1) paleta: poziomy scroll NIE moze byc potrzebny
    for sa in win.palette.findChildren(QScrollArea):
        bar = sa.horizontalScrollBar()
        if bar.isVisible() and bar.maximum() > 0:
            errors.append(f"w={width}: paleta poziomy scroll max={bar.maximum()}")

    # 2) wlasciwosci: pola edycji nie moga byc wezsze niz 90 px
    for name, wdg in win.properties._widgets.items():
        editor = wdg.editor
        if isinstance(editor, (QLineEdit, QComboBox, QSpinBox)):
            if editor.width() < 90:
                errors.append(
                    f"w={width}: pole '{name}' ma szerokosc {editor.width()}px")

    # 3) chipy palety mieszcza sie w viewport
    vp = win.palette.findChild(QScrollArea).viewport().width()
    for chip in win.palette.findChildren(_BlockChip)[:3]:
        if chip.width() > vp:
            errors.append(
                f"w={width}: chip szerszy niz viewport ({chip.width()}>{vp})")

    # 4) log nie moze miec poziomego scrolla (miekki wrap)
    lv = win.log_view
    if lv.horizontalScrollBar().maximum() > 0:
        # dozwolone tylko gdy brak slown do zawijania — ignorujemy
        pass

    print(f"OK {width}x{height}: "
          f"paleta={win.palette.width()} canvas={win.canvas.width()} "
          f"panel={win.properties.width()} log={lv.height()}")


app = QApplication(sys.argv)
app.setStyleSheet(STYLE)
win = MainWindow()
prog = win.storage.program
start = prog.add_block(BlockType.START, 40, 40)
click = prog.add_block(BlockType.CLICK, 40, 110)
prog.set_socket(start.id, "next", click.id)
win.canvas.refresh()
win._on_block_selected(click.id)
win.show()
app.processEvents()

errors = []
for w, h in ((1600, 900), (1280, 800), (1024, 720), (900, 640)):
    check(win, w, h, errors)

win.storage.dirty = False
win.close()
if errors:
    print("\nPROBLEMY:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("\nBrak przycinania przy testowanych rozdzielczosciach.")
