"""Przechwytywanie wycinka ekranu jako szablonu PNG.

Pełnoekranowy overlay (ramka bez zdobień) pokazuje swiezy zrzut ekranu;
uzytkownik zaznacza prostokat mysza — wyciecie trafia do TemplateRegistry.
Zrzut robi backend platformowy (mss), wiec dziatka tak samo na Windows i X11.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QImage, QMouseEvent, QPainter, QPen,
                           QGuiApplication, QPixmap)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from ..core.platform.base import MonitorInfo, ScreenBackend
from ..i18n import t
from . import theme
from .properties import monitor_combo_items


def _bgr_to_qimage(frame: np.ndarray) -> QImage:
    """BGR(A) ndarray (lub szary) -> QImage RGB32 (kopia bufora).

    Konwersja do 32 bit/px jest konieczna: Qt wymusza wyrównanie
    bytesPerLine do wielokrotności 4, a bufor numpy jest upakowany
    ciasno (bpl = w * kanaly). Przy formatach 24/8-bit i szerokosci
    niepodzielnej przez 4 kazdy wiersz byl przesuniety — podglad
    wygladal na 'sciagniety' pod katem, choc PNG na dysku (osobna
    sciezka cv2.imwrite) pozostawal poprawny. Format_RGBA8888 ma
    bpl = 4 * w, wiec jest zawsze zgodny z uklad pamieci.
    """
    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    buf = np.empty((h, w, 4), dtype=np.uint8)   # pamiec: R,G,B,A
    if frame.ndim == 2:
        buf[..., 0] = buf[..., 1] = buf[..., 2] = frame
    elif frame.shape[2] == 4:
        buf[..., 0] = frame[..., 2]
        buf[..., 1] = frame[..., 1]
        buf[..., 2] = frame[..., 0]
        buf[..., 3] = frame[..., 3]
        return QImage(bytes(buf), w, h, QImage.Format.Format_RGBA8888).copy()
    else:
        buf[..., 0] = frame[..., 2]
        buf[..., 1] = frame[..., 1]
        buf[..., 2] = frame[..., 0]
    buf[..., 3] = 255
    return QImage(bytes(buf), w, h, QImage.Format.Format_RGBA8888).copy()


class RegionPickerOverlay(QWidget):
    """Ciemny overlay na calym ekranie; zaznacz prostokat obszaru szablonu."""

    region_picked = Signal(int, int, int, int)   # x, y, w, h (ekran)
    cancelled = Signal()

    def __init__(self, frame: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self._frame = frame
        self._pixmap = QPixmap.fromImage(_bgr_to_qimage(frame))
        self._origin: Optional[QPointF] = None
        self._current: Optional[QPointF] = None
        self.setWindowFlags(Qt.WindowType.Window
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    # ---------------------------------------------------------------- rysowanie
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        rect = self._selection_rect()
        if rect is not None:
            painter.setClipRect(rect)
            painter.drawPixmap(self.rect(), self._pixmap)
            painter.setClipping(False)
            pen = QPen(QColor(theme.ACCENT_MARK), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
            painter.setPen(QPen(QColor("#FFFFFF"), 1))
            painter.drawText(rect.adjusted(4, -22, 0, -4),
                             Qt.AlignmentFlag.AlignLeft,
                             f"{rect.width()} × {rect.height()} px")
        else:
            painter.setPen(QPen(QColor("#FFFFFF")))
            painter.drawText(self.rect().adjusted(0, 80, 0, 0),
                             Qt.AlignmentFlag.AlignHCenter,
                             t("capture.overlay_hint"))
        painter.end()

    def _selection_rect(self) -> Optional[QRect]:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin.toPoint(),
                     self._current.toPoint()).normalized()

    # ---------------------------------------------------------------- mysz
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.position()
            self._current = e.position()
            self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = e.position()
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = self._selection_rect()
        self._origin = None
        if rect is None or rect.width() < 4 or rect.height() < 4:
            self.update()
            return
        self.region_picked.emit(rect.x(), rect.y(), rect.width(), rect.height())

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(e)


class CaptureDialog(QDialog):
    """Flow: wybor ekranu -> zrzut -> picker -> nazwa -> zapis do rejestru.

    Wybór ekranu (combo) zaweza zrzut do jednego monitora — przy 3+ ekranach
    overlay nie „rozlewa sie" po calym pulpicie, tylko przykrywa wskazany
    monitor. Wspolrzedne zaznaczenia przeliczane sa na piksele absolutne
    wirtualnego pulpitu (fizyczne), wiec szablon pasuje do szukania po
    regionie monitora. Emisja ``captured(template_id)`` po zapisie.
    """

    captured = Signal(str)

    def __init__(self, screen: ScreenBackend, registry, parent=None,
                 default_monitor: Optional[int] = None) -> None:
        super().__init__(parent)
        self.screen = screen
        self.registry = registry
        self._frame: Optional[np.ndarray] = None
        self._overlay: Optional[RegionPickerOverlay] = None
        #: prostokat (fizyczny) tego, co jest na biezacym zrzucie + offset
        self._shot_origin: Tuple[int, int] = (0, 0)
        self._overlay_geo = QRect()
        self.setWindowTitle(t("capture.title"))
        # Tryb bezmodalny: pelnoekranowy overlay jest innym top-levelem, a
        # modalny dialog (exec) gluszylby jego zdarzenia myszy/klawiatury.
        self.setModal(False)
        layout = QVBoxLayout(self)
        self.info = QLabel(t("capture.info"))
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        # wybor ekranu — ukryty gdy backend nie enumeruje monitorow
        row = QHBoxLayout()
        self.lbl_monitor = QLabel(t("capture.monitor"))
        self.combo_monitor = QComboBox()
        self.combo_monitor.setMinimumWidth(220)
        row.addWidget(self.lbl_monitor)
        row.addWidget(self.combo_monitor, 1)
        self._monitor_row = row
        layout.addLayout(row)
        self._refresh_monitors(default_monitor)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        layout.addWidget(self.status)
        self.btn = _CaptureButton(t("capture.btn"), self)
        self.btn.clicked.connect(self._start_pick)
        layout.addWidget(self.btn)

    # ------------------------------------------------------------- monitory
    def _monitor_list(self) -> list:
        try:
            fn = getattr(self.screen, "monitors", None)
            return list(fn()) if callable(fn) else []
        except Exception:  # pragma: no cover - backend bez enumeracji
            return []

    def _refresh_monitors(self, default_monitor: Optional[int]) -> None:
        monitors = self._monitor_list()
        self.lbl_monitor.setVisible(bool(monitors))
        self.combo_monitor.setVisible(bool(monitors))
        self.combo_monitor.clear()
        self.combo_monitor.addItem(t("props.monitor_all"), 0)
        for label, data in monitor_combo_items(monitors):
            self.combo_monitor.addItem(label, data)
        want = default_monitor or 0
        idx = self.combo_monitor.findData(int(want))
        if idx < 0:
            primary = next((m for m in monitors if m.is_primary), None)
            idx = self.combo_monitor.findData(primary.index) if primary else 0
        self.combo_monitor.setCurrentIndex(max(idx, 0))

    def _selected_monitor(self) -> Optional[MonitorInfo]:
        if not self.combo_monitor.isVisible():
            return None
        data = self.combo_monitor.currentData()
        if not data:
            return None
        return next((m for m in self._monitor_list() if m.index == int(data)),
                    None)

    # ----------------------------------------------------------------- flow
    def _start_pick(self) -> None:
        # Chowamy okna aplikacji (nie moga byc widoczne na zrzucie), a zrzut
        # robimy z opoznieniem, az system zdazy je ukryc.
        self._refresh_monitors(int(self.combo_monitor.currentData() or 0))
        self.status.setText(t("capture.hiding"))
        main = self.parentWidget()
        if main is not None:
            main.hide()
        self.hide()
        QTimer.singleShot(300, self._grab_and_pick)

    def _grab_and_pick(self) -> None:
        mon = self._selected_monitor()
        try:
            if mon is not None:
                self._frame = self.screen.grab(mon.region)
                self._shot_origin = (mon.region[0], mon.region[1])
            else:
                self._frame = self.screen.grab(None)
                vb = getattr(self.screen, "virtual_bounds", None)
                self._shot_origin = tuple(vb()[:2]) if callable(vb) else (0, 0)
        except Exception as exc:  # BackendError itp.
            self._restore_main()
            self.show()
            self.status.setText(t("capture.grab_error", exc=exc))
            return
        geo = self._overlay_geometry(mon)
        self._overlay_geo = geo
        overlay = RegionPickerOverlay(self._frame)
        self._overlay = overlay
        overlay.setGeometry(geo)
        overlay.region_picked.connect(self._on_region)
        overlay.cancelled.connect(self._on_cancel)
        if mon is not None or len(QGuiApplication.screens()) <= 1:
            overlay.showFullScreen()
        else:
            overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.grabKeyboard()

    def _overlay_geometry(self, mon: Optional[MonitorInfo]) -> QRect:
        """Geometria LOGICZNA Qt przykrywajaca to, co jest na zrzucie.

        Wybrany monitor -> geometria QScreen odpowiadajacego jego regionowi
        fizycznemu (dopasowanie po srodku regionu — niezawodne przy DPI).
        Wszystkie ekrany -> unia logicznych geometrii (virtualGeometry).
        """
        screens = QGuiApplication.screens() or []
        if not screens:  # pragma: no cover - QPA bez ekranu
            return QRect(0, 0, max(self._frame.shape[1], 1),
                         max(self._frame.shape[0], 1))
        if mon is not None:
            cx = mon.region[0] + mon.region[2] // 2
            cy = mon.region[1] + mon.region[3] // 2
            best = None
            for s in screens:
                if s.nativeGeometry().contains(cx, cy):
                    best = s
                    break
            if best is None:   # DPI/obce uklady: geometry po proporcjach
                best = screens[0]
            return best.geometry()
        virt = QApplication.primaryScreen().virtualGeometry()
        for s in screens:
            virt = virt.united(s.geometry())
        return virt

    def _dismiss_overlay(self) -> None:
        """Znika nakladka + zwalnia klawiature.

        Samo deleteLater() NIE wystarczy: DeferredDelete jest przetwarzane
        dopiero po powrocie do glownej petli zdarzen, a tuz po zaznaczeniu
        wchodzi zagniezdzony exec() (dialog nazwy) — okno
        WindowStaysOnTopHint zostaloby na ekranie i blokujolo mysz.
        """
        overlay, self._overlay = self._overlay, None
        if overlay is None:
            return
        overlay.releaseKeyboard()
        overlay.hide()
        overlay.deleteLater()

    def _on_region(self, x: int, y: int, w: int, h: int) -> None:
        """Zaznaczenie (logiczne, lokalne dla overlaya) -> crop + offset globalny."""
        assert self._frame is not None and self._overlay is not None
        self._dismiss_overlay()
        fh, fw = self._frame.shape[:2]
        ow = max(self._overlay_geo.width(), 1)
        oh = max(self._overlay_geo.height(), 1)
        # skala logiczne Qt -> fizyczne piksele zrzutu (dokladna: frame/overlay,
        # lepsza niz devicePixelRatio przy DPI ulamkowych 125%/150%)
        sx, sy = fw / ow, fh / oh
        px = int(round(x * sx))
        py = int(round(y * sy))
        pw = max(1, int(round(w * sx)))
        ph = max(1, int(round(h * sy)))
        px = max(0, min(px, fw - 1))
        py = max(0, min(py, fh - 1))
        pw = min(pw, fw - px)
        ph = min(ph, fh - py)
        crop = self._frame[py:py + ph, px:px + pw]
        gx = self._shot_origin[0] + px
        gy = self._shot_origin[1] + py
        self._restore_main()
        self.show()
        if crop.size == 0:
            self.status.setText(t("capture.outside"))
            return
        from .templates_panel import TemplateNameDialog
        dlg = TemplateNameDialog(crop, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.template_id():
            try:
                meta = self.registry.add_from_array(dlg.template_id(), crop)
            except Exception as exc:
                self.status.setText(t("capture.save_error", exc=exc))
                return
            self.status.setText(t("capture.saved", id=meta.id,
                                  w=meta.width, h=meta.height))
            self.captured.emit(meta.id)
            self.accept()   # sukces -> zamykamy okno przechwytywania

    def _on_cancel(self) -> None:
        assert self._overlay is not None
        self._dismiss_overlay()
        self._restore_main()
        self.show()
        self.raise_()
        self.activateWindow()

    def _restore_main(self) -> None:
        """Przywraca okno glowne ukryte przed zrzutem."""
        main = self.parentWidget()
        if main is None:
            return
        if not main.isVisible():
            main.showNormal()
        main.raise_()
        main.activateWindow()




class _CaptureButton(QWidget):
    """Prosty akcentowany przycisk (bez QPushButton-stylistyki systemu)."""

    clicked = Signal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        # QWidget::mousePressEvent() domyslnie ODRZUCA press, wtedy Qt nie
        # dostarcza temu widgetowi zwolnienia — bez accept() clicked nigdy by
        # nie zostal wyemitowany.
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton \
                and self.rect().contains(e.position().toPoint()):
            e.accept()
            self.clicked.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(theme.ACCENT_OK if self.isEnabled()
                          else theme.BG_PANEL))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 8, 8)
        p.setPen(QColor("#FFFFFF" if self.isEnabled()
                        else theme.TEXT_FAINT))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()
