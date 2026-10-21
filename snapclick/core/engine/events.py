"""Bus zdarzeń silnika — silnik nie zna GUI, tylko emituje zdarzenia.

GUI (główny wątek) konsumuje je np. przez ``threading`` kolejkę + QTimer
lub sygnały Qt. ``EventBus`` jest trywialnie thread-safe (jedna blokada).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventKind(str, Enum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"        # status: ok | stopped | error
    BLOCK_STARTED = "block_started"
    BLOCK_FINISHED = "block_finished"
    FOUND = "found"                      # szablon odnaleziony
    NOT_FOUND = "not_found"              # szablonu brak (po timeoutcie)
    ACTION = "action"                    # klik / wpis / klawisz
    LOG = "log"                          # dowolny komunikat dla logu
    ERROR = "error"


@dataclass(frozen=True)
class EngineEvent:
    kind: EventKind
    block_id: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # frozen dataclass + mutable default: ustawiamy przez object.__setattr__
        if self.data is None:
            object.__setattr__(self, "data", {})


Listener = Callable[[EngineEvent], None]


class EventBus:
    """Prosty pub/sub z listą słuchaczy i blokadą (emit z wielu wątków)."""

    def __init__(self) -> None:
        self._listeners: List[Listener] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Zapisuje słuchacza; zwraca funkcję wypisującą."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def emit(self, event: EngineEvent) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # słuchacz nie może wywalić silnika
                pass

    # skróty
    def log(self, message: str, block_id: Optional[str] = None) -> None:
        self.emit(EngineEvent(EventKind.LOG, block_id=block_id, message=message))
