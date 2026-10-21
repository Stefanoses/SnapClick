"""Paleta blokow — kategorie z klockami przeciąganymi na canvas."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt
from PySide6.QtGui import (QColor, QDrag, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core.model.blocks import BLOCK_META, BlockMeta
from ..i18n import t
from . import theme

MIME_BLOCK_TYPE = "application/x-m2-blocktype"
_CATEGORY_ORDER = ("events", "actions", "logic")


class _BlockChip(QFrame):
    """Minimalistyczny klocek w palecie: ciemne tlo + akcentowy pasek kategorii.

    Rysowany wlasnorecznie (paintEvent) zamiast QSS — pelna kontrola nad
    ksztaltem: zaokraglenie 8 px, plytkie wypelnienie w odcieniu kategorii,
    jaskrawy 4-px pasek po lewej (identyfikator) i wyrazna biala etykieta.
    Inicjuje QDrag po starcie myszy.
    """

    def __init__(self, meta: BlockMeta, parent=None) -> None:
        super().__init__(parent)
        self.meta = meta
        self._press_x = 0
        self._press_y = 0
        self._hover = False
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._fill = theme.block_fill(meta.color)
        self._border = theme.block_border(self._fill)
        self._accent = theme.block_accent(self._fill)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(0)
        self._label = label = QLabel(meta.label)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setStyleSheet(
            f"color:{theme.BLOCK_TEXT}; background:transparent;"
            "font-weight:600;")
        # Eliza = '...' gdy panel jest wezszy niz etykieta (responsywnosc;
        # wczesniej tekst byl po prostu ucinany przez maksimum panelu).
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setMinimumWidth(0)
        # Ignored: layout NIE bierze sizeHint etykiety jako minimum — inaczej
        # dluga etykieta rozepchnelaby chipa poza viewport scrolla (poziomy
        # scrollbar jest wlaczony) i zostala ucinana zamiast elidowana.
        label.setSizePolicy(QSizePolicy.Policy.Ignored,
                            QSizePolicy.Policy.Preferred)
        layout.addWidget(label, 1)

    # -- rysowanie ------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        body = QPainterPath()
        body.addRoundedRect(rect, 8, 8)
        fill = QColor(self._fill)
        if self._hover:
            fill = fill.lighter(122)
        painter.fillPath(body, fill)
        # akcentowy pasek kategorii (przyciety do ksztaltu chipa)
        painter.setClipPath(body)
        stripe = QRectF(rect.x(), rect.y(), 4, rect.height())
        painter.fillRect(stripe, self._accent)
        painter.setClipping(False)
        painter.setPen(QPen(self._border, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    # -- drag ----------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._press_x = int(event.position().x())
        self._press_y = int(event.position().y())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        dx = int(event.position().x()) - self._press_x
        dy = int(event.position().y()) - self._press_y
        if abs(dx) + abs(dy) < 6:
            return
        mime = QMimeData()
        mime.setData(MIME_BLOCK_TYPE, self.meta.type.value.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(10, pixmap.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Skracamy etykiete zamiast ja ucinac (wielokropek)."""
        super().resizeEvent(event)
        self.refresh_label()

    def refresh_label(self) -> None:
        """Etykieta w biezacym jezyku, elidowana do dostepnej szerokosci."""
        fm = self._label.fontMetrics()
        avail = max(self.width() - 24, 20)
        text = self.meta.label
        if fm.horizontalAdvance(text) > avail:
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, avail)
        self._label.setText(text)


class Palette(QWidget):
    """Lista kategorii z klockami (przeciągnij na canvas)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chips: List[_BlockChip] = []
        self._cat_labels: List[tuple] = []   # (QLabel, klucz_kategorii)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = header = QLabel(t("palette.title"))
        header.setObjectName("paletteHeader")
        header.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-weight:bold; font-size:12px;"
            f"padding:10px 12px 6px 12px; background:{theme.BG_PANEL};"
            f"border-bottom:1px solid {theme.BORDER_SOFT};")
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet(f"background:{theme.BG_PANEL};")
        column = QVBoxLayout(content)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(6)

        by_category: Dict[str, List[BlockMeta]] = {}
        for meta in BLOCK_META.values():
            by_category.setdefault(meta.category, []).append(meta)

        ordered = [c for c in _CATEGORY_ORDER if c in by_category]
        ordered += [c for c in by_category if c not in ordered]
        for category in ordered:
            cat = QLabel(t(f"cat.{category}").upper())
            cat.setStyleSheet(
                f"color:{theme.TEXT_FAINT}; font-weight:bold; font-size:11px;"
                "margin-top:8px; letter-spacing:1px;")
            column.addWidget(cat)
            self._cat_labels.append((cat, category))
            for meta in by_category[category]:
                chip = _BlockChip(meta)
                column.addWidget(chip)
                self._chips.append(chip)
        column.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Responsywnosc: tylko minimum — ZADNE maximum. Gorny limit szerokosci
        # wewnatrz QSplittera sprawial, ze panele 'obcinaly' wlasna tresc.
        self.setMinimumWidth(170)
        self.setStyleSheet(f"background:{theme.BG_PANEL};")

    def retranslate(self) -> None:
        """Przelacza nazwe panelu, kategorie i etykiety klockow."""
        self._header.setText(t("palette.title"))
        for label, cat_key in self._cat_labels:
            label.setText(t(f"cat.{cat_key}").upper())
        for chip in self._chips:
            chip.refresh_label()
