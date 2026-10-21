"""Glowne okno aplikacji: paleta | canvas | panele + pasek RUN/STOP + log.

Warstwa jezykowa: wszystkie teksty UI pobierane przez ``i18n.t()``;
menu 'Jezyk' przełącza katalog na zywo — ``_apply_language()`` odswieza
napisy statyczne i odbudowuje panele zalezne od tlumaczen.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QStatusBar,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core.engine.events import EngineEvent, EventKind
from ..core.model.serializer import program_to_dict
from ..core.paths import projects_dir
from ..core.platform.base import BackendError, MonitorInfo
from ..core.platform.detect import PlatformInfo, create_backends, detect_platform
from ..i18n import (LANGUAGES, get_lang, language_name,
                    off_language_changed, on_language_changed, set_lang, t)
from ..project.storage import ProjectStorage, StorageError
from .canvas import BlockCanvas
from .capture import CaptureDialog
from .palette import Palette
from .properties import PropertiesPanel
from .runner import Runner
from .settings_dialog import InputSettingsDialog
from .templates_panel import TemplatesPanel
from . import theme

_AUTOSAVE_MS = 30_000


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._status_key = "status.ready"
        self.setWindowTitle(t("app.title"))
        self.resize(1480, 880)

        self.storage = ProjectStorage()
        self.platform: PlatformInfo = detect_platform()
        self._backend_bundle = None          # leniwe: blad pokazemy przy RUN
        self._backend_error: Optional[str] = None

        # --- spolki UI
        self.palette = Palette()
        self.canvas = BlockCanvas()
        self.properties = PropertiesPanel()
        self.templates = TemplatesPanel()
        self.runner = Runner(self)

        self._build_layout()
        self._build_menu()

        # sygnaly
        self.canvas.block_selected.connect(self._on_block_selected)
        self.canvas.program_changed.connect(self._on_program_changed)
        self.canvas.status_message.connect(self._log)
        self.properties.block_edited.connect(self._on_block_edited)
        self.properties.block_delete_requested.connect(
            self.canvas.delete_selected)
        self.templates.templates_changed.connect(self._on_templates_changed)
        self.templates.btn_capture.clicked.connect(self._open_capture)
        self.runner.event.connect(self._on_engine_event)
        self.runner.finished.connect(self._on_run_finished)
        self.runner.hotkey_stop.connect(self._on_hotkey_stop)

        # przełączenie jezyka (rowniez gdy wywolane poza tym oknem)
        on_language_changed(self._on_language_changed)

        # autosave co 30 s jesli brudno
        self._autosave = QTimer(self)
        self._autosave.setInterval(_AUTOSAVE_MS)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start()

        self._new_project_quiet()
        self._log(t("log.platform",
                    os_name=self.platform.os_name,
                    session=self.platform.session))

        # monitory: provider dla panelu wlasciwosci + odswiezanie po zmianie
        # konfiguracji ekranow (hotplug / zmiana skalowania w Ustawieniach)
        self.properties.set_monitor_provider(self._monitor_options)
        self._refresh_monitor_combo()
        try:
            QGuiApplication.screenConfigChanged.connect(
                self._on_screen_config_changed)
        except Exception:  # pragma: no cover - platforma bez zdarzenia
            pass

    # ================================================================ layout
    def _build_layout(self) -> None:
        """Uklad w pelni responsywny.

        Zadnych `setMaximumWidth` — gorny limit wewnatrz QSplitter sprawial,
        ze panele 'obcinaly' wlasna zawartosc przy wezszym oknie. Zamiast
        tego: rozsadne minimow + stretch factory + mozliwosc przesuwania
        granic kazdego panelu (splittery poziomy i pionowy).
        """
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- pasek narzedzi
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_run = QPushButton(t("toolbar.run"))
        self.btn_run.setStyleSheet(
            f"background:{theme.ACCENT_OK};color:#FFFFFF;font-weight:bold;"
            "border:none;border-radius:7px;padding:8px 18px;"
            f"QPushButton:hover{{background:{theme.ACCENT_OK};}}"
            "QPushButton:disabled{background:#3A4048;color:#6E7682;}")
        self.btn_run.clicked.connect(self._run_clicked)
        self.btn_stop = QPushButton(t("toolbar.stop"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            f"background:{theme.ACCENT_STOP};color:#FFFFFF;font-weight:bold;"
            "border:none;border-radius:7px;padding:8px 18px;"
            "QPushButton:disabled{background:#3A4048;color:#6E7682;}")
        self.btn_stop.clicked.connect(self._stop_clicked)
        self.lbl_status = QLabel(t(self._status_key))
        self.lbl_status.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; padding-left:10px;")
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_stop)
        bar.addWidget(self.lbl_status, 1)

        # --- celowy monitor (domysla przestrzen wyszukiwania 'screen')
        lbl_mon = QLabel(t("toolbar.monitor"))
        lbl_mon.setStyleSheet(f"color:{theme.TEXT_MUTED};padding-left:8px;")
        bar.addWidget(lbl_mon)
        self.lbl_monitor = lbl_mon
        self.combo_monitor = QComboBox()
        self.combo_monitor.setToolTip(t("toolbar.monitor_tip"))
        self.combo_monitor.setMinimumWidth(190)
        self.combo_monitor.currentIndexChanged.connect(
            self._on_monitor_selected)
        bar.addWidget(self.combo_monitor)
        # podglad ukladu ekranow + szybki wybor (dwuklik na monitorze)
        self.btn_monitor_layout = QPushButton("▦")
        self.btn_monitor_layout.setToolTip(t("toolbar.layout_tip"))
        self.btn_monitor_layout.setFixedWidth(34)
        self.btn_monitor_layout.clicked.connect(self._open_monitor_layout)
        bar.addWidget(self.btn_monitor_layout)
        root.addLayout(bar)

        # --- glowny splitter: paleta | canvas | panele
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)
        self.splitter.addWidget(self.palette)

        self.canvas.setMinimumWidth(360)
        self.splitter.addWidget(self.canvas)

        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("rightTabs")
        self.right_tabs.setMinimumWidth(250)
        self.right_tabs.addTab(self.properties, t("tab.properties"))
        self.right_tabs.addTab(self.templates, t("tab.templates"))
        self.splitter.addWidget(self.right_tabs)

        # proporcje przy starcie i przy skalowaniu okna: canvas rosnie
        # najszybciej, paleta najwolniej
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([230, 820, 330])

        # --- log jako dolna sekcja pionowego splittera (przesuwna, zgnable)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText(t("log.placeholder"))
        self.log_view.setStyleSheet(
            f"background:{theme.BG_INPUT};color:{theme.TEXT_MUTED};"
            "font-family:Consolas,'Cascadia Mono',monospace;font-size:12px;"
            f"border:1px solid {theme.BORDER_SOFT};border-radius:6px;")
        self.log_view.setMinimumHeight(60)

        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.setChildrenCollapsible(False)
        vertical.setHandleWidth(6)
        vertical.addWidget(self.splitter)
        vertical.addWidget(self.log_view)
        vertical.setStretchFactor(0, 4)
        vertical.setStretchFactor(1, 1)
        vertical.setSizes([640, 150])
        root.addWidget(vertical, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_menu(self) -> None:
        # menu i akcje trzymane jako atrybuty — niezbedne do retranslacji
        self.menu_file = self.menuBar().addMenu(t("menu.file"))
        self.act_new = QAction(t("act.new"), self)
        self.act_new.setShortcut(QKeySequence("Ctrl+N"))
        self.act_new.triggered.connect(self._new_project)
        self.act_open = QAction(t("act.open"), self)
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open.triggered.connect(self._open_project)
        self.act_save = QAction(t("act.save"), self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.triggered.connect(self._save_project)
        self.act_saveas = QAction(t("act.saveas"), self)
        self.act_saveas.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_saveas.triggered.connect(self._save_project_as)
        self.act_quit = QAction(t("act.quit"), self)
        self.act_quit.setShortcut(QKeySequence("Alt+F4"))
        self.act_quit.triggered.connect(self.close)
        for a in (self.act_new, self.act_open, None, self.act_save,
                  self.act_saveas, None, self.act_quit):
            if a is None:
                self.menu_file.addSeparator()
            else:
                self.menu_file.addAction(a)

        self.menu_run = self.menuBar().addMenu(t("menu.run"))
        self.act_run = QAction(t("act.run"), self)
        self.act_run.setShortcut(QKeySequence("F5"))
        self.act_run.triggered.connect(self._run_clicked)
        self.act_stop = QAction(t("act.stop"), self)
        self.act_stop.setShortcut(QKeySequence("F10"))
        self.act_stop.triggered.connect(self._stop_clicked)
        self.act_settings = QAction(t("act.settings"), self)
        self.act_settings.triggered.connect(self._open_settings)
        self.menu_run.addAction(self.act_run)
        self.menu_run.addAction(self.act_stop)
        self.menu_run.addSeparator()
        self.menu_run.addAction(self.act_settings)

        # --- jezyk: radiowe, ponizej katalogu LANGUAGES
        self.menu_lang = self.menuBar().addMenu(t("menu.language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        self._lang_actions = {}
        for code in LANGUAGES:
            act = QAction(language_name(code), self)
            act.setCheckable(True)
            act.setChecked(get_lang() == code)
            act.triggered.connect(
                lambda _checked=False, c=code: set_lang(c))
            group.addAction(act)
            self.menu_lang.addAction(act)
            self._lang_actions[code] = act

    # ------------------------------------------------------------ jezyk
    def _on_language_changed(self, code: str) -> None:
        # Okno moze zostac zniszczone (deleteLater) pozniej niz nastapi
        # wyrejestrowanie sluchacza — guard chroni przed wolaniem na
        # niezyjacym obiekcie C++ (libshiboken RuntimeError).
        import shiboken6
        if not shiboken6.isValid(self):
            return
        for c, act in self._lang_actions.items():
            act.setChecked(c == code)
        self._apply_language()

    def _apply_language(self) -> None:
        """Retranslacja calego UI bez przebudowy widzetow tam, gdzie sie da."""
        self.menu_file.setTitle(t("menu.file"))
        self.menu_run.setTitle(t("menu.run"))
        self.menu_lang.setTitle(t("menu.language"))
        self.act_new.setText(t("act.new"))
        self.act_open.setText(t("act.open"))
        self.act_save.setText(t("act.save"))
        self.act_saveas.setText(t("act.saveas"))
        self.act_quit.setText(t("act.quit"))
        self.act_run.setText(t("act.run"))
        self.act_stop.setText(t("act.stop"))
        self.act_settings.setText(t("act.settings"))

        self.btn_run.setText(t("toolbar.run"))
        self.btn_stop.setText(t("toolbar.stop"))
        self.lbl_status.setText(t(self._status_key))
        # combo monitora: etykiety pozycji sa tlumaczone -> odbudowa zachowa
        # wybor (findData po wartosci, nie po tekście)
        self.lbl_monitor.setText(t("toolbar.monitor"))
        self.combo_monitor.setToolTip(t("toolbar.monitor_tip"))
        self.btn_monitor_layout.setToolTip(t("toolbar.layout_tip"))
        self._refresh_monitor_combo()

        self.right_tabs.setTabText(
            self.right_tabs.indexOf(self.properties), t("tab.properties"))
        self.right_tabs.setTabText(
            self.right_tabs.indexOf(self.templates), t("tab.templates"))
        self.log_view.setPlaceholderText(t("log.placeholder"))

        self.palette.retranslate()
        self.properties.retranslate()
        self.templates.retranslate()
        self.canvas.retranslate()

        self._update_title()

    # ============================================================= monitory
    def _monitor_options(self) -> list:
        """list[MonitorInfo] z backendu ekranu (leniwie).

        Gdy backend jest niedostepny (np. Wayland, CI bez X) zwracamy [] —
        combo pokazuje wowczas tylko 'wszystkie ekrany'. Nie budujemy listy
        z QGuiApplication: jej kolejnosc nie musi odpowiadac indeksom mss.
        """
        bundle = self._backend_bundle or self._backends()
        if bundle is None:
            return []
        try:
            return list(bundle.screen.monitors())
        except Exception:  # pragma: no cover - backend bez enumeracji
            return []

    def _current_monitor_value(self) -> int:
        program = self.storage.program
        return int(program.monitor or 0)

    def _refresh_monitor_combo(self) -> None:
        """Odbudowuje combo paska; wartosc = program.monitor (None ~ 0)."""
        from .properties import monitor_combo_items
        combo = self.combo_monitor
        current = self._current_monitor_value()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(t("props.monitor_all"), 0)
        for label, data in monitor_combo_items(self._monitor_options()):
            combo.addItem(label, data)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        # usuniete ekrany (hotplug): program wskazuje nieistniejacy indeks?
        stale = self.storage.program.monitor
        if stale and combo.findData(int(stale)) < 0:
            self.storage.program.monitor = None
            self.storage.dirty = True
            self._log(t("log.monitor_reset", idx=stale))

    def _on_monitor_selected(self, _index: int) -> None:
        program = self.storage.program
        if program is None:
            return
        data = self.combo_monitor.currentData()
        value = int(data) if data else None
        if program.monitor != value:
            program.monitor = value
            self._on_program_changed()

    def _on_screen_config_changed(self) -> None:
        """Hotplug / zmiana rozdzielczosci: odswiez liste ekranow UI."""
        # mss trzyma instancje per watrek; odswiezenie nastapi przy nastepnym
        # grab (nowy monitor list jest pobierany od backendu leniwie).
        self._refresh_monitor_combo()
        self.properties.reload_monitors(self._monitor_options())
        self._log(t("log.monitors_changed"))

    def _set_monitor(self, index: int) -> None:
        """Ustawia program.monitor (0/None = caly pulpit) i odswieza UI."""
        program = self.storage.program
        if program is None:
            return
        value = int(index) if index else None
        if program.monitor != value:
            program.monitor = value
            self._on_program_changed()
        self._refresh_monitor_combo()
        what = (t("props.monitor_all") if value is None
                else t("props.monitor_item", idx=value, label=""))
        self._log(t("log.monitor_set", what=what.strip(" ·")))

    def _open_monitor_layout(self) -> None:
        """Podglad ukladu ekranow; dwuklik na monitorze = wybor domyslny."""
        from .monitor_layout import MonitorLayoutDialog
        dlg = MonitorLayoutDialog(self._monitor_options,
                                  current=self._current_monitor_value(),
                                  parent=self)
        dlg.monitor_chosen.connect(self._set_monitor)
        dlg.exec()

    # ============================================================ projekty
    def _new_project_quiet(self) -> None:
        self.storage.new_project(projects_dir())
        self._attach_storage()

    def _attach_storage(self) -> None:
        assert self.storage.program is not None and self.storage.registry is not None
        self.canvas.set_program(self.storage.program)
        self.templates.set_registry(self.storage.registry)
        self.properties.set_block(None, self.templates.template_ids)
        self._refresh_monitor_combo()
        self._update_title()
        if self.storage.load_warning:
            self._log(t("log.warning", message=self.storage.load_warning))

    def _new_project(self) -> None:
        if not self._confirm_discard():
            return
        from PySide6.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(
            self, t("dlg.select_dir"))
        if not directory:
            return
        name, ok = QInputDialog.getText(self, t("dlg.new_project"),
                                        t("dlg.scenario_name"),
                                        text=t("project.shop_default"))
        if not ok:
            return
        try:
            self.storage.new_project(Path(directory), name)
        except Exception as exc:
            QMessageBox.critical(self, t("err.error"), str(exc))
            return
        self._attach_storage()
        self._log(t("log.created", path=self.storage.path))

    def _open_project(self) -> None:
        if not self._confirm_discard():
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, t("act.open"), "", t("file.filter"))
        if not path:
            return
        try:
            self.storage.load(Path(path))
        except StorageError as exc:
            QMessageBox.critical(self, t("err.open"), str(exc))
            return
        self._attach_storage()
        self._log(t("log.opened", path=self.storage.path))

    def _save_project(self) -> None:
        if self.storage.path is None:
            self._save_project_as()
            return
        try:
            self.storage.save()
        except Exception as exc:
            QMessageBox.critical(self, t("err.save"), str(exc))
            return
        self._update_title()
        self._log(t("log.saved", path=self.storage.path))

    def _save_project_as(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        suggested = str(self.storage.path) if self.storage.path else \
            f"{self.storage.program.name}{ProjectStorage.PROJECT_EXT}"
        path, _ = QFileDialog.getSaveFileName(
            self, t("dlg.save_as"), suggested, t("file.filter"))
        if not path:
            return
        try:
            self.storage.save_as(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, t("err.save"), str(exc))
            return
        self._attach_storage()
        self._log(t("log.saved", path=self.storage.path))

    def _confirm_discard(self) -> bool:
        if not self.storage.dirty:
            return True
        answer = QMessageBox.question(
            self, t("confirm.discard_title"), t("confirm.discard_text"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self._save_project()
            return not self.storage.dirty
        return True

    def _autosave_tick(self) -> None:
        if self.runner.running or not self.storage.dirty:
            return
        if self.storage.path is None:
            return
        try:
            backup = self.storage.path.with_suffix(
                ProjectStorage.PROJECT_EXT + ".autosave")
            data = json.dumps(
                program_to_dict(self.storage.program,
                                self.storage.registry.entries()),
                ensure_ascii=False, indent=2)
            backup.write_text(data, encoding="utf-8")
        except Exception:
            pass  # autosave nigdy nie przeszkadza

    def _update_title(self) -> None:
        name = self.storage.program.name if self.storage.program else "—"
        path = (self.storage.path.name if self.storage.path
                else t("project.unsaved"))
        mark = " *" if self.storage.dirty else ""
        self.setWindowTitle(t("app.title_doc", name=name, path=path, mark=mark))

    def _open_capture(self) -> None:
        """Narzedzie przechwycenia wycinka ekranu -> nowy szablon PNG."""
        bundle = self._backends()
        if bundle is None:
            QMessageBox.critical(self, t("err.no_backend"),
                                 self._backend_error or t("err.backend_unavailable"))
            return
        self._refresh_monitor_combo()
        dlg = CaptureDialog(bundle.screen, self.storage.registry, self,
                            default_monitor=self.storage.program.monitor)
        dlg.captured.connect(self._on_captured)
        # show() zamiast exec(): exec() wymusza modalnosc i gluszylby
        # pelnoekranowy overlay przechwycenia (inny top-level tej aplikacji).
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _on_captured(self, template_id: str) -> None:
        self.templates.refresh()
        self.properties.reload_template_choices(self.templates.template_ids())
        self.storage.dirty = True
        self._log(t("log.template_added", id=template_id))
        self._update_title()

    # ============================================================ canvas
    def _on_block_selected(self, block_id: Optional[str]) -> None:
        block = self.storage.program.get(block_id)
        self.properties.set_block(block, self.templates.template_ids)

    def _on_program_changed(self) -> None:
        self.storage.dirty = True
        self._update_title()

    def _on_block_edited(self) -> None:
        bid = None
        for item in self.canvas.items.values():
            if item.isSelected():
                bid = item.block.id
                break
        if bid:
            self.canvas.items[bid].refresh_geometry()
        self.storage.dirty = True
        self._update_title()

    def _on_templates_changed(self) -> None:
        self.storage.dirty = True
        self.properties.reload_template_choices(self.templates.template_ids())
        self._update_title()

    # ============================================================ uruchamianie
    def _backends(self):
        """Leniwa inicjalizacja backendow + komunikat o bledzie (np. Wayland)."""
        if self._backend_bundle is not None:
            return self._backend_bundle
        try:
            self._backend_bundle = create_backends(self.platform)
            self._backend_error = None
        except BackendError as exc:
            self._backend_error = str(exc)
            return None
        return self._backend_bundle

    def _run_clicked(self) -> None:
        if self.runner.running:
            return
        if self.storage.registry is None:
            return
        problems = self.storage.program.validate_problems()
        hard = [p.message for p in problems if p.hard]
        if hard:
            QMessageBox.warning(
                self, t("msg.incomplete"),
                t("msg.incomplete_body") + "\n\n• " + "\n• ".join(hard[:6]))
            return
        soft = [p.message for p in problems if not p.hard]
        if soft and QMessageBox.question(
                self, t("msg.warnings"),
                t("msg.warnings_body") + "\n\n• " + "\n• ".join(soft[:6])
                + t("msg.continue"),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                ) != QMessageBox.StandardButton.Yes:
            return
        bundle = self._backends()
        if bundle is None:
            QMessageBox.critical(self, t("err.no_backend"),
                                 self._backend_error or t("err.backend_unavailable"))
            return
        assert self.storage.registry is not None
        try:
            self.runner.start(self.storage.program, self.storage.registry,
                              bundle.screen, bundle.input, bundle.windows)
        except BackendError as exc:
            QMessageBox.critical(self, t("err.start"), str(exc))
            return
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_status("status.running")

    def _stop_clicked(self) -> None:
        self.runner.stop()
        self._set_status("status.stopping")

    def _open_settings(self) -> None:
        """Timing myszy / focus okna — zapisywane do settings.json na zywo."""
        dlg = InputSettingsDialog(self)
        dlg.exec()

    def _set_status(self, key: str) -> None:
        self._status_key = key
        self.lbl_status.setText(t(key))

    def _on_hotkey_stop(self) -> None:
        self._stop_clicked()

    # ----------------------------------------------------------- zdarzenia
    def _on_engine_event(self, ev: EngineEvent) -> None:
        if ev.kind is EventKind.BLOCK_STARTED:
            self.canvas.set_active_block(ev.block_id)
            label = ev.data.get("label", ev.message)
            self._log(f"▶ {label}")
        elif ev.kind is EventKind.FOUND and ev.data.get("center"):
            self.canvas.set_found_marker(tuple(ev.data["center"]))
        elif ev.kind is EventKind.ACTION:
            self._log(f"   {ev.message}")
        elif ev.kind is EventKind.LOG:
            self._log(f"   {ev.message}")
        elif ev.kind is EventKind.ERROR:
            self._log(f"✖ {ev.message}")
        elif ev.kind is EventKind.RUN_FINISHED:
            self.canvas.set_active_block(None)
            self.canvas.set_found_marker(None)

    def _on_run_finished(self, status: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        key = {"ok": "status.ok", "stopped": "status.stopped",
               "error": "status.error"}.get(status)
        label = t(key) if key else status
        self._set_status(key if key else "status.ready")
        if key is None:
            self.lbl_status.setText(label)
        self._log(f"— {label}")

    # ============================================================ log/out
    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.runner.running:
            self.runner.stop()
            self.runner.wait(2.0)
        if not self._confirm_discard():
            event.ignore()
            return
        self._autosave.stop()
        off_language_changed(self._on_language_changed)
        event.accept()
