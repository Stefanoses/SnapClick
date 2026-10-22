"""Regresja: awaria watka silnika NIE moze zawiesic GUI na 'Stopping…'.

Scenariusz buga (Linux/X11): ``Interpreter.run()`` rzucil
AttributeError('get_error_handler') ponad wlasnym try/except (setup
backendu okien lezal poza ochrona). ``Runner._run_safely`` zlapal wyjatek,
wrzucil tylko ERROR i zakonczyl watek — bez RUN_FINISHED pump QTimer
nigdy sie nie zatrzymal, sygnal ``finished`` nie zostal wyemitowany, a
przyciski Run/Stop zostaly zablokowane na zawsze (ratowal tylko restart).
"""
from __future__ import annotations

import queue

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 wymagany")


@pytest.fixture(scope="module")
def qapp_instance():
    from PySide6.QtWidgets import QApplication
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # brak dostepnego QPA (np. CI bez ekranu)
        pytest.skip(f"QApplication niedostepny: {exc}")
    yield app


class _BoomInterpreter:
    """Silnik, ktory wywala sie ZANIM zdazy emitowac RUN_FINISHED."""

    def run(self, ctx):
        raise AttributeError("get_error_handler")


def _drain_queue(runner):
    events = []
    while True:
        try:
            events.append(runner._queue.get_nowait())
        except queue.Empty:
            return events


def test_run_safely_emits_run_finished_after_thread_crash(qapp_instance):
    """Po wyjtku watka kolejka musi dostac ERROR + RUN_FINISHED(error)."""
    from snapclick.core.engine.events import EventKind
    from snapclick.gui.runner import Runner

    runner = Runner()
    runner._run_safely(_BoomInterpreter())

    events = _drain_queue(runner)
    kinds = [ev.kind for ev in events]
    assert EventKind.ERROR in kinds, "awaria watka musi byc zlogowana"
    assert kinds[-1] is EventKind.RUN_FINISHED, (
        "bez RUN_FINISHED pump sie nie zatrzyma i GUI wisi na 'Stopping…'")
    assert events[-1].data.get("status") == "error"


def test_drain_emits_finished_signal_after_crash(qapp_instance):
    """Koniec koncow: sygnal finished przywraca przyciski w MainWindow."""
    from snapclick.gui.runner import Runner

    runner = Runner()
    runner._run_safely(_BoomInterpreter())

    statuses = []
    runner.finished.connect(statuses.append)
    runner._drain()
    assert statuses == ["error"]
    assert not runner._pump.isActive()
