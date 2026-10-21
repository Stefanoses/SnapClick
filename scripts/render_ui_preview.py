"""Render okna glownego do PNG (podglad motywu bez pokazywania na ekranie)."""
import sys

from PySide6.QtWidgets import QApplication

from snapclick.core.model.blocks import BlockType
from snapclick.gui.main_window import MainWindow

app = QApplication(sys.argv)
from snapclick.gui.theme import STYLE
app.setStyleSheet(STYLE)

win = MainWindow()
prog = win.storage.program
start = prog.add_block(BlockType.START, 40, 40)
click = prog.add_block(BlockType.CLICK, 40, 110)
prog.set_socket(start.id, "next", click.id)
iff = prog.add_block(BlockType.IF_FOUND, 40, 190)
prog.set_socket(click.id, "next", iff.id)
prog.add_block(BlockType.WAIT, 70, 260)
win.canvas.refresh()
win.resize(1480, 880)
win.show()
app.processEvents()
pix = win.grab()
pix.save("ui_preview.png")
print("saved ui_preview.png", pix.width(), "x", pix.height())
