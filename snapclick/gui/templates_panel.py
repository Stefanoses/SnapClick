"""Panel szablonow PNG + dialog nazwy z podgladem wycinka."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..core.vision.templates import TemplateRegistry
from ..i18n import t
from .capture import _bgr_to_qimage
from . import theme


class TemplateNameDialog(QDialog):
    """Podglad przechwyconego wycinka + nazwa (id) szablonu."""

    def __init__(self, crop: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("tpl_dlg.title"))
        self.setModal(True)
        self.resize(420, 300)
        layout = QVBoxLayout(self)

        preview_host = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(160, 80)
        self.preview.setStyleSheet(
            f"background:{theme.BG_INPUT};"
            f"border:1px solid {theme.BORDER_SOFT}; border-radius:6px;")
        pix = QPixmap.fromImage(_bgr_to_qimage(crop))
        self.preview.setPixmap(pix.scaled(
            380, 180, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        preview_host.addWidget(self.preview)
        layout.addLayout(preview_host)

        form = QFormLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(t("tpl_dlg.placeholder"))
        self.edit.setText(self._suggest(crop))
        form.addRow(t("tpl_dlg.name"), self.edit)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @staticmethod
    def _suggest(crop: np.ndarray) -> str:
        # sugestia zawsze po angielsku — ID szablonu to trwaly identyfikator
        # w projekcie, niezalezny od jezyka UI
        return f"template_{crop.shape[1]}x{crop.shape[0]}"

    def template_id(self) -> str:
        return self.edit.text().strip()

    def _accept(self) -> None:
        from ..core.platform.base import BackendError
        try:
            TemplateRegistry.validate_id(self.template_id())
        except BackendError as exc:
            QMessageBox.warning(self, t("tpl_dlg.bad_name"), str(exc))
            return
        self.accept()


class TemplatesPanel(QWidget):
    """Lista szablonow projektu: dodaj z pliku / usun / odswiez."""

    templates_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.registry: Optional[TemplateRegistry] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)
        self._title = title = QLabel(t("tpl_panel.title"))
        title.setStyleSheet(
            f"font-weight:bold; font-size:14px; color:{theme.TEXT};")
        outer.addWidget(title)

        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 34))
        self.list.setSpacing(2)
        outer.addWidget(self.list, 1)

        # przyciski w dwóch rzędach — przy wąskim panelu sie nie ucinaja
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_capture = QPushButton(t("tpl_panel.capture"))
        self.btn_file = QPushButton(t("tpl_panel.file"))
        self.btn_remove = QPushButton(t("tpl_panel.remove"))
        row.addWidget(self.btn_capture, 3)
        row.addWidget(self.btn_file, 2)
        row.addWidget(self.btn_remove, 1)
        outer.addLayout(row)

        self.hint = QLabel(t("tpl_panel.hint"))
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:12px;")
        outer.addWidget(self.hint)
        # tylko minimum — zadnego gornego limitu (obcinal tresc panelu)
        self.setMinimumWidth(230)

        self.btn_file.clicked.connect(self._add_from_file)
        self.btn_remove.clicked.connect(self._remove_selected)

    # ------------------------------------------------------------------ API
    def set_registry(self, registry: Optional[TemplateRegistry]) -> None:
        self.registry = registry
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        if self.registry is None:
            return
        for t_id in self.registry.ids:
            item = QListWidgetItem(self._icon_for(t_id), t_id)
            item.setData(Qt.ItemDataRole.UserRole, t_id)
            self.list.addItem(item)

    def _icon_for(self, t_id: str) -> QIcon:
        if self.registry is None:
            return QIcon()
        try:
            img = self.registry.get(t_id)
        except Exception:
            return QIcon()
        pix = QPixmap.fromImage(_bgr_to_qimage(img)).scaled(
            72, 34, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        return QIcon(pix)

    def template_ids(self) -> List[str]:
        return self.registry.ids if self.registry else []

    # ------------------------------------------------------------- akcje
    def _add_from_file(self) -> None:
        if self.registry is None:
            return
        from PySide6.QtWidgets import QFileDialog
        import cv2
        path, _ = QFileDialog.getOpenFileName(
            self, t("tpl_file.title"), "", t("tpl_file.filter"))
        if not path:
            return
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            QMessageBox.warning(self, t("err.error"),
                                t("tpl.load_fail", path=path))
            return
        dlg = TemplateNameDialog(img, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.template_id():
            try:
                self.registry.add_from_array(dlg.template_id(), img)
            except Exception as exc:
                QMessageBox.warning(self, t("err.save"), str(exc))
                return
            self.refresh()
            self.templates_changed.emit()

    def _remove_selected(self) -> None:
        if self.registry is None:
            return
        item = self.list.currentItem()
        if item is None:
            return
        t_id = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(
                self, t("tpl.remove_title"), t("tpl.remove_body", id=t_id),
                ) != QMessageBox.StandardButton.Yes:
            return
        self.registry.remove(t_id)
        self.refresh()
        self.templates_changed.emit()

    # --------------------------------------------------------------- jezyk
    def retranslate(self) -> None:
        """Przelacza statyczne napisy panelu."""
        self._title.setText(t("tpl_panel.title"))
        self.btn_capture.setText(t("tpl_panel.capture"))
        self.btn_file.setText(t("tpl_panel.file"))
        self.btn_remove.setText(t("tpl_panel.remove"))
        self.hint.setText(t("tpl_panel.hint"))
