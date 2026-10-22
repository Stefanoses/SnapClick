"""Dialog ustawien timingu wejscia i focusu okna.

Wartosci trafiaja do ``snapclick.core.settings`` (settings.json) — backendy
Win32/X11 oraz interpreter czytaja je bezposrednio, wiec zmiana dziala od
nastepnego klikniecia bez restartu aplikacji.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QLabel, QVBoxLayout)

from ..core.settings import InputSettings, get_settings, set_settings
from ..i18n import t


def _seconds_spin(value: float, lo: float, hi: float, step: float) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setDecimals(3)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setSuffix(" s")
    w.setValue(value)
    return w


class InputSettingsDialog(QDialog):
    """Edycja InputSettings z podpowiedziami (kiedy co krecic)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("dlg.settings_title"))
        self.setMinimumWidth(430)
        st = get_settings()

        root = QVBoxLayout(self)
        hint = QLabel(t("dlg.settings_hint"))
        hint.setWordWrap(True)
        root.addWidget(hint)

        # --- metody wejścia (klik i tekst — niezależne)
        method_box = QGroupBox(t("dlg.settings_method"))
        mform = QFormLayout(method_box)
        self.cb_method = QComboBox()
        self.cb_method.addItem(t("choice.method_sendinput"), "sendinput")
        self.cb_method.addItem(t("choice.method_postmessage"), "postmessage")
        idx = self.cb_method.findData(st.click_method)
        self.cb_method.setCurrentIndex(max(idx, 0))
        mform.addRow(t("set.click_method"), self.cb_method)

        self.cb_type_method = QComboBox()
        self.cb_type_method.addItem(t("choice.auto"), "auto")
        self.cb_type_method.addItem(t("choice.method_sendinput"), "sendinput")
        self.cb_type_method.addItem(t("choice.method_postmessage"), "postmessage")
        self.cb_type_method.addItem(t("choice.method_clipboard"), "clipboard")
        idx = self.cb_type_method.findData(st.type_method)
        self.cb_type_method.setCurrentIndex(max(idx, 0))
        mform.addRow(t("set.type_method"), self.cb_type_method)

        mh = QLabel(t("set.click_method_hint"))
        mh.setWordWrap(True)
        mform.addRow(mh)
        root.addWidget(method_box)

        # --- timing myszy
        mouse_box = QGroupBox(t("dlg.settings_mouse"))
        form = QFormLayout(mouse_box)
        self.sp_hold = _seconds_spin(st.mouse_hold_s, 0.0, 2.0, 0.01)
        self.sp_settle = _seconds_spin(st.move_settle_s, 0.0, 2.0, 0.01)
        self.sp_gap = _seconds_spin(st.double_gap_s, 0.01, 1.0, 0.01)
        self.sp_release = _seconds_spin(st.release_settle_s, 0.0, 2.0, 0.01)
        self.sp_key_hold = _seconds_spin(st.key_hold_s, 0.0, 2.0, 0.005)
        self.sp_mod_settle = _seconds_spin(st.mod_settle_s, 0.0, 2.0, 0.005)
        form.addRow(t("set.mouse_hold"), self.sp_hold)
        form.addRow(t("set.move_settle"), self.sp_settle)
        form.addRow(t("set.double_gap"), self.sp_gap)
        form.addRow(t("set.release_settle"), self.sp_release)
        form.addRow(t("set.key_hold"), self.sp_key_hold)
        form.addRow(t("set.mod_settle"), self.sp_mod_settle)
        root.addWidget(mouse_box)

        # --- focus okna
        focus_box = QGroupBox(t("dlg.settings_focus"))
        fform = QFormLayout(focus_box)
        self.cb_focus = QCheckBox(t("set.focus_enabled"))
        self.cb_focus.setChecked(st.focus_enabled)
        self.cb_focus_per_click = QCheckBox(t("set.focus_after_click"))
        self.cb_focus_per_click.setChecked(st.focus_after_click)
        self.sp_focus_delay = _seconds_spin(st.focus_delay_s, 0.0, 5.0, 0.05)
        fform.addRow(self.cb_focus)
        fform.addRow(self.cb_focus_per_click)
        fform.addRow(t("set.focus_delay"), self.sp_focus_delay)
        root.addWidget(focus_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults
                       ).clicked.connect(self._restore_defaults)
        root.addWidget(buttons)

    # ------------------------------------------------------------- wyniki
    def current(self) -> InputSettings:
        return InputSettings(
            click_method=str(self.cb_method.currentData()),
            type_method=str(self.cb_type_method.currentData()),
            mouse_hold_s=self.sp_hold.value(),
            move_settle_s=self.sp_settle.value(),
            double_gap_s=self.sp_gap.value(),
            release_settle_s=self.sp_release.value(),
            key_hold_s=self.sp_key_hold.value(),
            mod_settle_s=self.sp_mod_settle.value(),
            focus_enabled=self.cb_focus.isChecked(),
            focus_after_click=self.cb_focus_per_click.isChecked(),
            focus_delay_s=self.sp_focus_delay.value(),
        )

    def _accept(self) -> None:
        set_settings(self.current())  # persist do settings.json
        self.accept()

    def _restore_defaults(self) -> None:
        d = InputSettings()
        idx = self.cb_method.findData(d.click_method)
        self.cb_method.setCurrentIndex(max(idx, 0))
        idx = self.cb_type_method.findData(d.type_method)
        self.cb_type_method.setCurrentIndex(max(idx, 0))
        self.sp_hold.setValue(d.mouse_hold_s)
        self.sp_settle.setValue(d.move_settle_s)
        self.sp_gap.setValue(d.double_gap_s)
        self.sp_release.setValue(d.release_settle_s)
        self.sp_key_hold.setValue(d.key_hold_s)
        self.sp_mod_settle.setValue(d.mod_settle_s)
        self.cb_focus.setChecked(d.focus_enabled)
        self.cb_focus_per_click.setChecked(d.focus_after_click)
        self.sp_focus_delay.setValue(d.focus_delay_s)
