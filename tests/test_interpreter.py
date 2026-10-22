"""Testy interpretera na mockowanych backendach (bez ekranu i myszy)."""
from __future__ import annotations

import numpy as np

from snapclick.core.engine.context import RunContext
from snapclick.core.engine.events import EventBus, EventKind
from snapclick.core.engine.interpreter import Interpreter
from snapclick.core.model.blocks import BlockType
from snapclick.core.model.program import Program

from conftest import FakeInput, FakeScreen, FakeTemplateRegistry, FakeWindows

# prosta "scena": 200x200 jednolite tło + przycisk w (120, 80)
BUTTON = np.full((20, 40, 3), 210, dtype=np.uint8)
BUTTON[3:17, 3:37] = (10, 10, 200)


def make_scene(button_visible: bool = True) -> np.ndarray:
    scene = np.zeros((200, 200, 3), dtype=np.uint8)
    if button_visible:
        scene[80:100, 120:160] = BUTTON
    return scene


def build_interpreter(button_visible: bool = True, registry_ids=None):
    program = Program(name="test")
    templates = {"button": BUTTON}
    registry = FakeTemplateRegistry(registry_ids or templates)
    screen = FakeScreen(lambda region: make_scene(button_visible))
    inp = FakeInput()
    events = EventBus()
    return program, Interpreter(program, registry, screen, inp,
                                FakeWindows(), events), inp, events


def test_click_found_template():
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START, 0, 0)
    click = program.add_block(BlockType.CLICK, 0, 40)
    click.params["template"] = "button"
    click.params["timeout"] = 0.1
    program.set_socket(start.id, "next", click.id)

    seen = []
    events.subscribe(lambda e: seen.append(e))
    status = interp.run()
    assert status == "ok"
    assert ("click", 140, 90, "left", False) in inp.actions
    assert any(e.kind is EventKind.FOUND for e in seen)


def test_run_survives_window_backend_crash():
    """Regresja X11: awaria backendu okien przy starcie (find_region lezal
    poza try/except) nie moze wywrocic run() — RUN_FINISHED musi byc
    wyemitowany, inaczej GUI wisi na 'Stopping…'."""
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params["template"] = "button"
    click.params["timeout"] = 0.1
    program.set_socket(start.id, "next", click.id)

    class BrokenWindows:
        def list_windows(self):
            raise AttributeError("get_error_handler")

        def find_region(self, title_substr):
            raise AttributeError("get_error_handler")

        def activate(self, title_substr):
            raise AttributeError("get_error_handler")

    interp.windows = BrokenWindows()
    interp.program.window_title = "MyApp"

    seen = []
    events.subscribe(lambda e: seen.append(e))
    status = interp.run()
    assert status == "ok"
    assert any(e.kind is EventKind.RUN_FINISHED for e in seen)
    # przebieg kontynuuje bez regionu okna (szukanie na calym ekranie)
    assert ("click", 140, 90, "left", False) in inp.actions


def test_click_not_found_stops():
    program, interp, inp, events = build_interpreter(button_visible=False)
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params["template"] = "button"
    click.params["timeout"] = 0.05
    click.params["poll"] = 0.01
    program.set_socket(start.id, "next", click.id)

    status = interp.run()
    assert status == "error"
    assert not any(a[0] == "click" for a in inp.actions)


def test_if_found_takes_then_branch():
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START)
    ifb = program.add_block(BlockType.IF_FOUND)
    ifb.params.update(template="button", timeout=0.05, poll=0.01)
    then_act = program.add_block(BlockType.TYPE_TEXT)
    then_act.params["text"] = "THEN"
    else_act = program.add_block(BlockType.TYPE_TEXT)
    else_act.params["text"] = "ELSE"
    program.set_socket(start.id, "next", ifb.id)
    program.set_socket(ifb.id, "then", then_act.id)
    program.set_socket(ifb.id, "else", else_act.id)

    assert interp.run() == "ok"
    typed = [a[1] for a in inp.actions if a[0] == "type"]
    assert typed == ["THEN"]


def test_if_found_takes_else_branch():
    program, interp, inp, events = build_interpreter(button_visible=False)
    start = program.add_block(BlockType.START)
    ifb = program.add_block(BlockType.IF_FOUND)
    ifb.params.update(template="button", timeout=0.02, poll=0.01)
    then_act = program.add_block(BlockType.TYPE_TEXT)
    then_act.params["text"] = "THEN"
    else_act = program.add_block(BlockType.TYPE_TEXT)
    else_act.params["text"] = "ELSE"
    program.set_socket(start.id, "next", ifb.id)
    program.set_socket(ifb.id, "then", then_act.id)
    program.set_socket(ifb.id, "else", else_act.id)

    assert interp.run() == "ok"
    typed = [a[1] for a in inp.actions if a[0] == "type"]
    assert typed == ["ELSE"]


def test_while_respects_max_iterations():
    """Przycisk cały czas widoczny -> pętla musi zbić się na limicie."""
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START)
    loop = program.add_block(BlockType.WHILE_FOUND)
    loop.params.update(template="button", threshold=0.95,
                       max_iterations=3, iteration_delay=0.0)
    body = program.add_block(BlockType.KEY_PRESS)
    body.params["combo"] = "esc"
    program.set_socket(start.id, "next", loop.id)
    program.set_socket(loop.id, "body", body.id)

    assert interp.run() == "ok"
    assert sum(a[0] == "combo" for a in inp.actions) == 3


def test_repeat_n_times():
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START)
    rep = program.add_block(BlockType.REPEAT)
    rep.params["count"] = 4
    body = program.add_block(BlockType.KEY_PRESS)
    body.params["combo"] = "enter"
    program.set_socket(start.id, "next", rep.id)
    program.set_socket(rep.id, "body", body.id)

    assert interp.run() == "ok"
    assert sum(a[0] == "combo" for a in inp.actions) == 4


def test_stop_interrupts_run():
    program, interp, inp, events = build_interpreter(button_visible=True)
    start = program.add_block(BlockType.START)
    loop = program.add_block(BlockType.WHILE_FOUND)
    loop.params.update(template="button", max_iterations=10000,
                       iteration_delay=0.01)
    body = program.add_block(BlockType.KEY_PRESS)
    body.params["combo"] = "a"
    program.set_socket(start.id, "next", loop.id)
    program.set_socket(loop.id, "body", body.id)

    ctx = RunContext()
    events.subscribe(lambda e: ctx.request_stop()
                     if e.kind is EventKind.BLOCK_STARTED
                     and e.block_id == body.id else None)
    status = interp.run(ctx)
    assert status == "stopped"
    # zatrzymanie po pierwszym wywołaniu body — nie 10000
    assert sum(a[0] == "combo" for a in inp.actions) <= 2


def test_validation_blocks_run():
    program, interp, inp, events = build_interpreter()
    program.add_block(BlockType.CLICK)  # brak START
    errors = []
    interp.events.subscribe(lambda e: errors.append(e)
                            if e.kind is EventKind.ERROR else None)
    assert interp.run() == "error"
    assert any("START" in e.message for e in errors)


def test_wait_block_respects_stop():
    program, interp, inp, events = build_interpreter()
    start = program.add_block(BlockType.START)
    wait = program.add_block(BlockType.WAIT)
    wait.params["seconds"] = 30.0
    after = program.add_block(BlockType.KEY_PRESS)
    program.set_socket(start.id, "next", wait.id)
    program.set_socket(wait.id, "next", after.id)

    import threading
    ctx = RunContext()
    threading.Timer(0.05, ctx.request_stop).start()
    import time
    t0 = time.monotonic()
    status = interp.run(ctx)
    assert status == "stopped"
    assert time.monotonic() - t0 < 5  # nie czeka pełnych 30 s
