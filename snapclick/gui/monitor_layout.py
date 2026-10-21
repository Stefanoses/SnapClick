"""Wizualny podgląd układu monitorów (mapa wirtualnego pulpitu).

Moduł ma dwie warstwy:

* ``scale_layout`` — czysta funkcja (bez Qt) skalująca prostokąty monitorów
  (takze z ujemnymi wspolrzednymi ekranow na lewo/ponad glownym) do okienka
  o zadanym rozmiarze. Oddzielona, by dac sie latwo testowac bez GUI.
* ``MonitorLayoutDialog`` — dialog rysujacy uklad; dwuklik na ekranie ustawia
  go jako domyslny monitor wyszukiwania (emituje ``monitor_chosen``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..i18n import t
from . import theme


@dataclass(frozen=True)
class ScaledMonitor:
    """Prostokat monitora w ukladzie okienka + odwolanie do MonitorInfo."""

    index: int
    rect: Tuple[float, float, float, float]  # (x, y, w, h) w pikselach widgetu
    monitor: object
    is_primary: bool


def scale_layout(monitors: Sequence, box_w: float, box_h: float,
                 margin: float = 12.0) -> Tuple[List[ScaledMonitor], float]:
    """Skaluje uklad monitorow do okienka ``(box_w, box_h)``.

    Pulpit wirtualny (prostokat ograniczajacy wszystkie ekrany — moze
    zaczynac sie w ujemnych wspolrzednych) skalujemy z zachowaniem
    proporcji i centrujemy w okienku. Zwraca ``(items, scale)``; dla
    pustej listy ``([], 1.0)``.
    """
    mons = [m for m in (monitors or []) if getattr(m, "region", None)]
    if not mons or box_w <= 0 or box_h <= 0:
        return [], 1.0
    x0 = min(m.region[0] for m in mons)
    y0 = min(m.region[1] for m in mons)
    x1 = max(m.region[0] + m.region[2] for m in mons)
    y1 = max(m.region[1] + m.region[3] for m in mons)
    vw = max(1, x1 - x0)
    vh = max(1, y1 - y0)
    avail_w = max(1.0, float(box_w) - 2.0 * margin)
    avail_h = max(1.0, float(box_h) - 2.0 * margin)
    scale = min(avail_w / vw, avail_h / vh)
    off_x = margin + (avail_w - vw * scale) / 2.0
    off_y = margin + (avail_h - vh * scale) / 2.0
    items = [
        ScaledMonitor(
            index=int(m.index),
            rect=(off_x + (m.region[0] - x0) * scale,
                  off_y + (m.region[1] - y0) * scale,
                  m.region[2] * scale, m.region[3] * scale),
            monitor=m,
            is_primary=bool(getattr(m, "is_primary", False)),
        )
        for m in mons
    ]
    return items, scale


class _LayoutView(QWidget):
    """Rysuje przeskalowane prostokaty monitorow; dwuklik = wybor ekranu."""

    monitor_activated = Signal(int)   # indeks mss monitora (1..N)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: List[ScaledMonitor] = []
        self._selected: Optional[int] = None
        self.setMinimumSize(360, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_monitors(self, monitors: Sequence,
                     selected: Optional[int]) -> None:
        self._selected = selected
        self._relayout()

    def set_selected(self, selected: Optional[int]) -> None:
        self._selected = selected
        self.update()

    def _relayout(self) -> None:
        self._items, _ = scale_layout(self._source_monitors(),
                                      self.width(), self.height())
        self.update()

    # podklada moze nadpisac zrodlo (testy GUI wstrzykuja liste statyczna)
    _source = None

    def set_source(self, monitors: Sequence) -> None:
        self._source = list(monitors)
        self._relayout()

    def _source_monitors(self) -> Sequence:
        return self._source or []

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._relayout()

    def _hit(self, pos: QPoint) -> Optional[ScaledMonitor]:
        # od konca: monitor rysowany pozniej (np. zaznaczony) wygrywa
        for item in reversed(self._items):
            if QRectF(*item.rect).contains(float(pos.x()), float(pos.y())):
                return item
        return None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        item = self._hit(event.position().toPoint())
        if item is not None:
            self.monitor_activated.emit(item.index)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG_INPUT))
        for item in self._items:
            x, y, w, h = item.rect
            sel = (self._selected is not None and item.index == self._selected)
            fill = QColor(theme.ACCENT if sel else theme.BG_PANEL)
            if sel:
                fill.setAlpha(90)
            p.setPen(QPen(QColor(theme.ACCENT if sel else theme.BORDER),
                          2 if sel else 1))
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
            p.setPen(QPen(QColor(theme.TEXT if sel else theme.TEXT_MUTED)))
            label = f"{item.index}"
            if item.is_primary:
                label += " ★"
            p.drawText(QRectF(x, y, w, h),
                       Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class MonitorLayoutDialog(QDialog):
    """Podglad ukladu ekranow + szybki wybor monitora domyslnego.

    ``monitor_provider`` — funkcja zwracajaca ``list[MonitorInfo]`` (ta sama
    co w toolbarze; leniwa, moze zwrocic [] gdy backend niedostepny).
    ``monitor_chosen(index)`` — 1..N = wybor, 0 = 'wszystkie ekrany'.
    """

    monitor_chosen = Signal(int)

    def __init__(self, monitor_provider, current: Optional[int] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("layout.title"))
        self.resize(520, 360)
        self._provider = monitor_provider
        self._current = int(current or 0)

        root = QVBoxLayout(self)
        info = QLabel(t("layout.hint"))
        info.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        info.setWordWrap(True)
        root.addWidget(info)

        self.view = _LayoutView(self)
        self.view.monitor_activated.connect(self._on_activated)
        root.addWidget(self.view, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_all = QPushButton(t("layout.all"))
        self.btn_all.clicked.connect(lambda: self._choose(0))
        self.btn_close = QPushButton(t("layout.close"))
        self.btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_all)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.refresh()

    def refresh(self) -> None:
        try:
            monitors = list(self._provider() or [])
        except Exception:  # pragma: no cover - backend bez enumeracji
            monitors = []
        self.view.set_source(monitors)
        self.view.set_selected(self._current or None)

    def _on_activated(self, index: int) -> None:
        self._choose(int(index))

    def _choose(self, index: int) -> None:
        self._current = index
        self.view.set_selected(index or None)
        self.monitor_chosen.emit(index)
