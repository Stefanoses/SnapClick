"""Sterowanie uruchomieniem scenariusza w watku roboczym.

GUI nigdy nie czeka na silnik: ``Runner.start()`` odpala wątek, a zdarzenia
trafiaja do kolejki; ``QTimer`` w watku glownym je 'odpompowowuje' i emituje
sygnaly Qt (podswietlanie blokow, log). STOP = przycisk lub globalny F10.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.engine.context import RunContext
from ..core.engine.events import EngineEvent, EventKind
from ..core.engine.interpreter import Interpreter
from ..core.model.program import Program
from ..core.platform.base import (BackendError, InputBackend, ScreenBackend,
                                  WindowBackend)
from ..core.vision.templates import TemplateRegistry
from ..i18n import t


class Runner(QObject):
    """Pojedyncze uruchomienie scenariusza (watek) + mostek zdarzen do Qt."""

    event = Signal(object)          # EngineEvent
    finished = Signal(str)          # status: ok | stopped | error
    hotkey_stop = Signal()          # F10 wcisnety

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._ctx: Optional[RunContext] = None
        self._queue: "queue.Queue[EngineEvent]" = queue.Queue()
        self._pump = QTimer(self)
        self._pump.setInterval(40)
        self._pump.timeout.connect(self._drain)
        self._hotkey_listener = None

    # ------------------------------------------------------------------ API
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, program: Program, registry: TemplateRegistry,
              screen: ScreenBackend, input_backend: InputBackend,
              windows: Optional[WindowBackend]) -> None:
        """Uruchamia watek silnika. Wczesniej STOP nie jest wymagany."""
        if self.running:
            raise BackendError(t("runner.already_running"))
        self._ctx = RunContext()
        interpreter = Interpreter(program, registry, screen,
                                  input_backend, windows)
        bus = interpreter.events
        bus.subscribe(self._queue.put)
        self._thread = threading.Thread(
            target=self._run_safely, args=(interpreter,),
            name="snapclick-engine", daemon=True)
        self._pump.start()
        self._thread.start()
        self._start_hotkey()

    def stop(self) -> None:
        if self._ctx is not None:
            self._ctx.request_stop()

    def wait(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------- wewnetrzne
    def _run_safely(self, interpreter: Interpreter) -> None:
        try:
            status = interpreter.run(self._ctx)
        except Exception as exc:  # pragma: no cover — ostatnia linia obrony
            status = "error"
            self._queue.put(EngineEvent(
                EventKind.ERROR, message=t("runner.thread_error", exc=repr(exc))))
        # Interpreter sam emituje RUN_FINISHED przez swoj bus (podsluchany
        # wyzej) — nie dublujemy go; kolejka go dostarczy i pump zamknie.

    def _drain(self) -> None:
        """Przenosi zdarzenia z kolejki do sygnalow Qt (watki glowny)."""
        drained = 0
        while drained < 200:
            try:
                ev = self._queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self.event.emit(ev)
            if ev.kind.value == "run_finished":
                self._pump.stop()
                self._stop_hotkey()
                self.finished.emit(str(ev.data.get("status", "error")))

    # ------------------------------------------------------------ hotkey F10
    def _start_hotkey(self) -> None:
        if self._hotkey_listener is not None:
            return
        try:
            from pynput import keyboard

            def on_activate() -> None:
                # sygnal Qt emitowany z watku pynput — bezpieczny (queued)
                self.hotkey_stop.emit()

            listener = keyboard.GlobalHotKeys({"<f10>": on_activate})
            listener.daemon = True
            listener.start()
            self._hotkey_listener = listener
        except Exception:
            # np. Wayland bez dostepu do globalnego wejscia — przycisk STOP
            # w oknie nadal dziala, wiec tylko logujemy faktyczna utrate.
            self._hotkey_listener = None

    def _stop_hotkey(self) -> None:
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
