"""Panel wlasciwosci wybranego bloku — widgety generowane z ParamSpec."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from ..core.model.blocks import BLOCK_META, Block, BlockType, ParamSpec
from ..i18n import choice_label, t
from . import theme


def monitor_combo_items(monitors: List) -> "list[tuple[str, int]]":
    """Pozycje 1..N combo monitora: ``(etykieta, indeks)``.

    Uzywane i w panelu wlasciwosci (parametr 'monitor' bloku), i w toolbarze
    okna glownego — etykiety musza byc identyczne w obu miejscach.
    """
    items = []
    for m in monitors:
        label = t("props.monitor_item", idx=m.index, label=m.label)
        if getattr(m, "is_primary", False):
            label += " " + t("props.monitor_primary")
        items.append((label, int(m.index)))
    return items


class _ParamWidget(QWidget):
    """Jeden wiersz: etykieta + edytor wartosci parametru."""

    value_changed = Signal()

    def __init__(self, spec: ParamSpec, template_ids_provider: Callable[[], List[str]],
                 parent=None) -> None:
        super().__init__(parent)
        self.spec = spec
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.editor = self._make_editor(spec, template_ids_provider)
        layout.addWidget(self.editor, 1)
        self._refresh_btn = None
        if spec.kind == "template":
            self._refresh_btn = _MiniButton("↻")
            self._refresh_btn.clicked.connect(
                lambda: self.reload_choices(template_ids_provider()))
            layout.addWidget(self._refresh_btn)

    def _make_editor(self, spec: ParamSpec, provider) -> QWidget:
        if spec.kind == "bool":
            w = QCheckBox()
            w.stateChanged.connect(lambda *_: self.value_changed.emit())
            return w
        if spec.kind == "int":
            w = QSpinBox()
            w.setRange(int(spec.min_value if spec.min_value is not None else -1_000_000),
                       int(spec.max_value if spec.max_value is not None else 1_000_000))
            w.valueChanged.connect(lambda *_: self.value_changed.emit())
            return w
        if spec.kind == "float":
            w = QDoubleSpinBox()
            w.setDecimals(2)
            w.setRange(float(spec.min_value if spec.min_value is not None else 0.0),
                       float(spec.max_value if spec.max_value is not None else 1e6))
            w.setSingleStep(0.05 if spec.max_value and spec.max_value <= 1 else 0.1)
            w.valueChanged.connect(lambda *_: self.value_changed.emit())
            return w
        if spec.kind == "monitor":
            # Wartosci: None = dziedzicz z paska 'Monitor', 0 = wszystkie
            # ekrany (pulpit wirtualny), 1..N = fizyczny monitor backendu.
            w = QComboBox()
            self._fill_monitor_combo(w, [])
            w.currentIndexChanged.connect(lambda *_: self.value_changed.emit())
            return w
        if spec.kind in ("choice", "template"):
            w = QComboBox()
            if spec.kind == "choice":
                # addItem z userData = SUROWA wartosc (zawsze EN, trafia do
                # projektu), a text = tlumaczona etykieta. addItems() nie
                # ustawia UserRole -> duplikaty przy findData (regresja).
                for choice in spec.choices:
                    w.addItem(choice_label(str(choice)), str(choice))
            else:
                self._fill_combo(w, provider())
            w.currentIndexChanged.connect(lambda *_: self.value_changed.emit())
            return w
        # text / keycombo / region — pole tekstowe
        w = QLineEdit()
        w.editingFinished.connect(self.value_changed)
        if spec.key == "window_title":
            w.setPlaceholderText(t("props.window_title_hint"))
        return w

    def retranslate(self) -> None:
        """Po zmianie jezyka odswieza etykiety wartosci w combo 'choice'
        (userData — a wiec i wartosc w projekcie — pozostaje bez zmian)."""
        if self.spec.kind != "choice" or not isinstance(self.editor, QComboBox):
            return
        combo = self.editor
        current = combo.currentData()
        combo.blockSignals(True)
        for i, choice in enumerate(self.spec.choices):
            if i < combo.count() and combo.itemData(i) == str(choice):
                combo.setItemText(i, choice_label(str(choice)))
        if current is not None:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    @staticmethod
    def _fill_combo(combo: QComboBox, ids: List[str]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(t("props.no_template"), "")
        for tid in ids:
            combo.addItem(tid, tid)
        if current:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    @staticmethod
    def _fill_monitor_combo(combo: QComboBox, monitors: List) -> None:
        """Lista monitorow jako ``list[MonitorInfo]`` (+ pseudo-wartosci).

        userData: None (dziedzicz) / 0 (wszystkie ekrany) / 1..N. findData
        nie rozroznia None od braku — szukamy recznie po porownaniu 'is None'.
        """
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(t("props.monitor_inherit"), None)
        combo.addItem(t("props.monitor_all"), 0)
        for label, data in monitor_combo_items(monitors):
            combo.addItem(label, data)
        idx = 0
        if current is not None:
            found = combo.findData(current)
            if found >= 0:
                idx = found
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def reload_choices(self, ids: List[str]) -> None:
        if self.spec.kind == "template" and isinstance(self.editor, QComboBox):
            self._fill_combo(self.editor, ids)

    def reload_monitors(self, monitors: List) -> None:
        if self.spec.kind == "monitor" and isinstance(self.editor, QComboBox):
            self._fill_monitor_combo(self.editor, monitors)

    # ------------------------------------------------------------- wartosc
    def set_value(self, value) -> None:
        self.editor.blockSignals(True)
        try:
            if self.spec.kind == "monitor":
                assert isinstance(self.editor, QComboBox)
                if value is None or value == "":
                    self.editor.setCurrentIndex(0)
                else:
                    found = self.editor.findData(int(value))
                    self.editor.setCurrentIndex(max(found, 0))
            elif self.spec.kind == "bool":
                assert isinstance(self.editor, QCheckBox)
                self.editor.setChecked(bool(value))
            elif self.spec.kind == "int":
                assert isinstance(self.editor, QSpinBox)
                self.editor.setValue(int(value or 0))
            elif self.spec.kind == "float":
                assert isinstance(self.editor, QDoubleSpinBox)
                self.editor.setValue(float(value or 0.0))
            elif self.spec.kind in ("choice", "template"):
                assert isinstance(self.editor, QComboBox)
                text = str(value or "")
                idx = self.editor.findData(text)
                if idx < 0:
                    idx = self.editor.findText(text)
                if idx < 0 and self.spec.kind == "choice":
                    # wartosc spoza listy (np. recznie edytowany plik) —
                    # doklejam, ale tylko gdy napewno jej nie ma
                    self.editor.addItem(text, text)
                    idx = self.editor.count() - 1
                self.editor.setCurrentIndex(max(idx, 0))
            else:
                assert isinstance(self.editor, QLineEdit)
                self.editor.setText("" if value is None else str(value))
        finally:
            self.editor.blockSignals(False)

    def value(self):
        if self.spec.kind == "monitor":
            assert isinstance(self.editor, QComboBox)
            data = self.editor.currentData()
            return None if data is None else int(data)
        if self.spec.kind == "bool":
            assert isinstance(self.editor, QCheckBox)
            return self.editor.isChecked()
        if self.spec.kind == "int":
            assert isinstance(self.editor, QSpinBox)
            return int(self.editor.value())
        if self.spec.kind == "float":
            assert isinstance(self.editor, QDoubleSpinBox)
            return float(self.editor.value())
        if self.spec.kind in ("choice", "template"):
            assert isinstance(self.editor, QComboBox)
            data = self.editor.currentData()
            return data if data is not None else self.editor.currentText()
        assert isinstance(self.editor, QLineEdit)
        return self.editor.text()


class _MiniButton(QWidget):
    """Male 'przycisk' odswiezania listy szablonow."""

    clicked = Signal()

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self.setFixedSize(26, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QColor, QFont, QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(theme.BG_HOVER))
        p.setPen(QColor(theme.BORDER))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)
        p.setPen(QColor(theme.TEXT))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class PropertiesPanel(QWidget):
    """Buduje formularz dla wybranego bloku; zapisuje edycje do modelu."""

    block_edited = Signal()          # canvas ma odswiezyc etykiety
    block_delete_requested = Signal()  # uzyskownik kliknal "Usuń blok"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._block: Optional[Block] = None
        self._widgets: Dict[str, _ParamWidget] = {}
        self._suspend = False
        self._tpl_provider: Optional[Callable[[], List[str]]] = None
        # Lista MonitorInfo (uzupelniana przez wlasciciela okna) + leniwy
        # provider — combo 'monitor' czyta je przy budowie formularza.
        self._monitors: List = []
        self._monitor_provider: Optional[Callable[[], List]] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._form_host = QWidget()
        self._form = QVBoxLayout(self._form_host)
        self._form.setContentsMargins(12, 12, 12, 12)
        self._form.setSpacing(8)
        self._placeholder = QLabel(t("props.placeholder"))
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self._form.addWidget(self._placeholder)
        self._form.addStretch(1)
        self._scroll.setWidget(self._form_host)
        outer.addWidget(self._scroll)

        # stale widoczny pasek akcji wybranego bloku (Delete usuwa to samo)
        actions = QHBoxLayout()
        actions.setContentsMargins(12, 4, 12, 10)
        self.btn_delete = QPushButton(t("props.delete"))
        self.btn_delete.setToolTip(t("props.delete_tip"))
        self.btn_delete.setEnabled(False)
        self.btn_delete.setStyleSheet(
            f"QPushButton{{background:{theme.ACCENT_STOP};color:#FFFFFF;"
            "border:none;border-radius:6px;padding:7px 12px;"
            "font-weight:bold;}"
            f"QPushButton:disabled{{background:{theme.BG_PANEL};"
            f"color:{theme.TEXT_FAINT};}}")
        self.btn_delete.clicked.connect(self.block_delete_requested)
        actions.addWidget(self.btn_delete)
        outer.addLayout(actions)

        # Responsywnosc: minimum dla czytelnych etykiet; ZADNE maximum
        # (sztywny gorony limit obcinat formularz we wskim splitterze).
        self.setMinimumWidth(230)

    # ------------------------------------------------------------------ API
    def set_monitor_provider(self, provider: Callable[[], List]) -> None:
        self._monitor_provider = provider

    def reload_monitors(self, monitors: List) -> None:
        """Nowa konfiguracja ekranow: cache + odswizenie otwartych combo."""
        self._monitors = list(monitors)
        for pw in self._widgets.values():
            pw.reload_monitors(self._monitors)

    def set_block(self, block: Optional[Block],
                  template_ids_provider: Callable[[], List[str]]) -> None:
        self._block = block
        self._tpl_provider = template_ids_provider
        if self._monitor_provider is not None:
            try:
                self._monitors = list(self._monitor_provider())
            except Exception:  # backend ekranu jeszcze niedostepny
                pass
        self._clear_form()
        self.btn_delete.setEnabled(block is not None
                                   and block.type is not BlockType.START)
        if block is None:
            self._form.insertWidget(0, self._placeholder)
            return
        meta = BLOCK_META[block.type]
        title = QLabel(meta.label)
        title.setStyleSheet(
            f"font-weight:bold; font-size:14px; color:{theme.TEXT};"
            "padding:2px 0;")
        self._form.insertWidget(0, title)
        if not meta.params:
            hint = QLabel(t("props.no_params"))
            hint.setStyleSheet(f"color:{theme.TEXT_MUTED};")
            self._form.insertWidget(1, hint)
            return
        box = QGroupBox(t("props.parameters"))
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        for spec in meta.params:
            pw = _ParamWidget(spec, template_ids_provider)
            pw.value_changed.connect(self._commit)
            if spec.kind == "monitor":
                # combo uzupelniamy PRZED set_value — przy nieobecnym
                # wyborze findData zwroci -1 i wartosc by sie zgubila
                pw.reload_monitors(self._monitors)
            pw.set_value(block.param(spec.key))
            # Etykieta z wordWrap + gorny limit szerokosci: przy wezszym
            # panelu lamie sie do kilku linii zamiast zgniotac pole edycji.
            caption = QLabel(spec.label + ":")
            caption.setWordWrap(True)
            caption.setMaximumWidth(150)
            form.addRow(caption, pw)
            self._widgets[spec.key] = pw
        self._form.insertWidget(1, box)

    def reload_template_choices(self, ids: List[str]) -> None:
        for pw in self._widgets.values():
            pw.reload_choices(ids)

    def retranslate(self) -> None:
        """Przelacz jezyk: statyczne napisy + odbudowa formularza biezacego
        bloku (tytul, groupbox, etykiety parametrow, combo choice)."""
        self._placeholder.setText(t("props.placeholder"))
        self.btn_delete.setText(t("props.delete"))
        self.btn_delete.setToolTip(t("props.delete_tip"))
        if self._block is None or self._tpl_provider is None:
            return
        provider = self._tpl_provider
        block = self._block
        # wstrzymuj commit — odbudowa nie moze nadpisac parametrow wartosciami
        # domyslnymi zanim ustawimy set_value() z modelu
        self._suspend = True
        try:
            self.set_block(block, provider)
        finally:
            self._suspend = False

    # ------------------------------------------------------------- wewnetrzne
    def _clear_form(self) -> None:
        self._widgets.clear()
        while self._form.count():
            item = self._form.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._placeholder:
                w.deleteLater()

    def _commit(self) -> None:
        """Zapisuje wartosci widgetow do bloku (po jednej zmianie)."""
        if self._suspend or self._block is None:
            return
        for key, pw in self._widgets.items():
            value = pw.value()
            if self._block.params.get(key) != value:
                self._block.params[key] = value
        self.block_edited.emit()
