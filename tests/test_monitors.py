"""Testy wielomonitorowe: 3 ekrany (dwa na dole obok siebie, trzeci na gorze).

Uklad scenariusza (wspolrzedne wirtualnego pulpitu, piksele fizyczne)::

    monitor 1 (glowny, dol-lewo):  (0, 0, 640, 256)
    monitor 2 (dol-prawo):         (640, 0, 640, 256)
    monitor 3 (gora, ujemne Y):    (320, -256, 640, 256)
    pulpit wirtualny:              (0, -256, 1280, 512)

Cel: regresja ujemnych wspolrzednych — klik na gornym monitorze musi trafic
w (400, -200), zarowno przy wskazanym monitorze jak i przy region=None.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from snapclick.core.engine.context import RunContext
from snapclick.core.engine.events import EventBus, EventKind
from snapclick.core.engine.interpreter import Interpreter
from snapclick.core.model.blocks import BlockType
from snapclick.core.model.program import Program
from snapclick.core.model.serializer import load_program_dict, program_to_dict
from snapclick.core.platform.base import MonitorInfo

from conftest import FakeInput, FakeScreen, FakeTemplateRegistry

# ------------------------------------------------------------------ scena
MONITORS = [
    MonitorInfo(index=1, region=(0, 0, 640, 256), is_primary=True),
    MonitorInfo(index=2, region=(640, 0, 640, 256)),
    MonitorInfo(index=3, region=(320, -256, 640, 256)),
]
VIRTUAL = (0, -256, 1280, 512)

#: przycisk 40x20 srodek w (400, -200) — lezy na gornym monitorze
BUTTON = np.full((20, 40, 3), 210, dtype=np.uint8)
BUTTON[3:17, 3:37] = (10, 10, 200)
ABS_TARGET = (400, -200)


def render(region):
    """Klatka dla regionu (lub calej sumy wirtualnej, region=None)."""
    x, y, w, h = VIRTUAL if region is None else region
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    bx, by = ABS_TARGET[0] - x - 20, ABS_TARGET[1] - y - 10
    if 0 <= bx and 0 <= by and by + 20 <= h and bx + 40 <= w:
        frame[by:by + 20, bx:bx + 40] = BUTTON
    return frame


class RecordingScreen(FakeScreen):
    """FakeScreen zapamietujacy regiony, z ktorych robiono zrzut."""

    def __init__(self) -> None:
        super().__init__(render, monitors=MONITORS)
        self.regions: list = []

    def grab(self, region=None):
        self.regions.append(region)
        return super().grab(region)


def build(program_monitor=None, block_monitor=None):
    """START -> CLICK(szablon 'btn'); zwraca takze blok click do rozbudowy."""
    program = Program(name="multi")
    program.monitor = program_monitor
    registry = FakeTemplateRegistry({"btn": BUTTON})
    screen = RecordingScreen()
    inp = FakeInput()
    events = EventBus()
    interp = Interpreter(program, registry, screen, inp, None, events)
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params.update(template="btn", timeout=0.05, poll=0.01,
                        post_wait=0.0)
    if block_monitor is not None:
        click.params["monitor"] = block_monitor
    program.set_socket(start.id, "next", click.id)
    return program, interp, inp, events, screen, click


# ------------------------------------------------- MonitorInfo / etykiety
def test_monitor_info_label_format():
    assert MONITORS[0].label == "640x256+0+0"
    # ujemne wspolrzedne musza zostac widoczne w etykiecie (znak minus)
    assert MONITORS[2].label == "640x256+320+-256"


def test_monitor_combo_items_labels_and_primary():
    from snapclick.gui.properties import monitor_combo_items
    items = monitor_combo_items(MONITORS)
    assert [data for _, data in items] == [1, 2, 3]
    # etykieta zawiera indeks, rozmiar i cwiartke 'primary' dla monitora 1
    assert "1" in items[0][0] and "640x256+0+0" in items[0][0]
    assert items[0][0].endswith("(główny)")
    assert not items[1][0].endswith("(główny)")


# ------------------------------------------------------ parsowanie w mss
def test_mss_backend_parses_monitors_with_negative_coords(monkeypatch):
    """MssScreenBackend.monitors()/virtual_bounds() na sfałszowanym mss."""
    raw = [
        {"left": 0, "top": -256, "width": 1280, "height": 512},   # suma
        {"left": 0, "top": 0, "width": 640, "height": 256},       # glowny
        {"left": 640, "top": 0, "width": 640, "height": 256},
        {"left": 320, "top": -256, "width": 640, "height": 256},  # gora
    ]

    class FakeSct:
        monitors = raw

    fake_mss = types.ModuleType("mss")
    fake_mss.mss = lambda: FakeSct()
    monkeypatch.setitem(sys.modules, "mss", fake_mss)

    from snapclick.core.platform._mss_screen import MssScreenBackend
    be = MssScreenBackend()
    mons = be.monitors()
    assert [m.index for m in mons] == [1, 2, 3]
    assert mons[0].is_primary and not mons[2].is_primary
    assert mons[2].region == (320, -256, 640, 256)
    assert be.virtual_bounds() == (0, -256, 1280, 512)
    assert be.primary_size() == (640, 256)


# ------------------------------------------------ RunContext: cache + origin
def test_run_caches_monitors_and_virtual_origin():
    _program, interp, _inp, _ev, screen, _click = build()
    ctx = RunContext()
    interp.run(ctx)
    assert ctx.monitors == {1: (0, 0, 640, 256),
                            2: (640, 0, 640, 256),
                            3: (320, -256, 640, 256)}
    assert ctx.virtual_origin == (0, -256)


def test_monitor_cache_not_refetched_per_block():
    """Tablice monitorow pobieramy RAZ na przebieg (cache w ctx)."""
    _p, interp, _inp, _ev, _s, _c = build()
    ctx = RunContext(monitors={m.index: m.region for m in MONITORS},
                     virtual_origin=(0, -256))
    calls = {"n": 0}
    orig = interp.screen.monitors

    def counting():
        calls["n"] += 1
        return orig()

    interp.screen.monitors = counting
    assert interp.run(ctx) == "ok"
    assert calls["n"] == 0          # ctx.monitors wypelnione -> bez wywolania


# -------------------------------------------------- priorytet wyboru monitora
def test_block_monitor_overrides_program_monitor():
    """Parametr bloku (2) wygrywa z program.monitor (3)."""
    _p, interp, _inp, _ev, screen, click = build(program_monitor=3,
                                                 block_monitor=2)
    click.params["on_fail"] = "continue"   # przycisku na monitorze 2 nie ma
    ctx = RunContext()
    assert interp.run(ctx) == "ok"
    assert screen.regions[0] == (640, 0, 640, 256)


def test_program_monitor_used_when_block_inherits():
    """Blok bez wlasnego monitora dziedziczy program.monitor."""
    _p, interp, _inp, _ev, screen, click = build(program_monitor=3)
    click.params["on_fail"] = "continue"
    ctx = RunContext()
    assert interp.run(ctx) == "ok"
    assert screen.regions[0] == (320, -256, 640, 256)


def test_monitor_zero_or_none_means_whole_desktop():
    """program.monitor=0/None i blok bez nadpisania -> region=None."""
    for pm in (None, 0):
        _p, interp, _inp, _ev, screen, _c = build(program_monitor=pm)
        ctx = RunContext()
        assert interp.run(ctx) == "ok"
        assert screen.regions[0] is None


# ----------------------------------------- przeliczanie ujemnych wspolrzednych
def test_click_negative_y_with_monitor_selected():
    """Region = gorny monitor (320,-256): srodek (80,60) klatki -> (400,-196)?

    Nie: srodek w klatce monitora to (400-320, -200-(-256)) = (80, 56);
    po przesunieciu o rog regionu klik ma trafic DOKLADNIE w (400, -200).
    """
    _p, interp, inp, _ev, _s, _c = build(program_monitor=3)
    ctx = RunContext()
    assert interp.run(ctx) == "ok"
    clicks = [a for a in inp.actions if a[0] == "click"]
    assert clicks == [("click", 400, -200, "left", False)]


def test_click_negative_y_with_region_none_full_desktop():
    """region=None: zrzut startuje w (0,-256) — offset liczymy od origin.

    Regresja: stary kod dolozyl (0,0) i kliknal o 256 px za nisko.
    """
    _p, interp, inp, _ev, _s, _c = build(program_monitor=None)
    ctx = RunContext()
    assert interp.run(ctx) == "ok"
    clicks = [a for a in inp.actions if a[0] == "click"]
    assert clicks == [("click", 400, -200, "left", False)]


def test_click_offset_applied_on_negative_monitor():
    """offset_x/offset_y dokladaja sie DO wspolrzednych absolutnych."""
    _p, interp, inp, _ev, _s, click = build(program_monitor=3)
    click.params.update(offset_x=5, offset_y=-7)
    ctx = RunContext()
    assert interp.run(ctx) == "ok"
    assert ("click", 405, -207, "left", False) in inp.actions


# ------------------------------------------------ fallback + ostrzezenie w logu
def test_missing_monitor_falls_back_with_warning():
    """program.monitor=9 (nie istnieje) -> log LOG + szukanie po calym pulpicie."""
    _p, interp, inp, events, screen, _c = build(program_monitor=9)
    logs = []
    events.subscribe(lambda e: logs.append(e) if e.kind is EventKind.LOG else None)
    ctx = RunContext()
    assert interp.run(ctx) == "ok"          # klik i tak trafia (pulpit widzi cel)
    assert screen.regions[0] is None        # fallback: caly pulpit
    assert any("9" in (e.message or "") for e in logs)
    assert ("click", 400, -200, "left", False) in inp.actions


def test_missing_monitor_warns_once_per_run():
    """W petli ostrzezenie raz na przebieg, nie przy kazdym bloku."""
    program, interp, _inp, events, _s, click = build(program_monitor=9)
    rep = program.add_block(BlockType.REPEAT)
    rep.params["count"] = 3
    click2 = program.add_block(BlockType.CLICK)
    click2.params.update(template="btn", timeout=0.02, poll=0.01,
                         post_wait=0.0, on_fail="continue")
    program.set_socket(click.id, "next", rep.id)
    program.set_socket(rep.id, "body", click2.id)
    logs = []
    events.subscribe(lambda e: logs.append(e) if e.kind is EventKind.LOG else None)
    assert interp.run(RunContext()) == "ok"
    monitor_logs = [e for e in logs if "9" in (e.message or "")]
    assert len(monitor_logs) == 1


# ------------------------------------------------------ serializacja monitora
def test_serializer_roundtrip_program_monitor():
    program = Program(name="x", window_title="MyApp", monitor=3)
    data = program_to_dict(program)
    assert data["monitor"] == 3
    restored, _ = load_program_dict(data)
    assert restored.monitor == 3


def test_serializer_monitor_none_and_garbage():
    program = Program(name="x")
    data = program_to_dict(program)
    assert data["monitor"] is None
    restored, _ = load_program_dict(data)
    assert restored.monitor is None
    # smieci w polu monitor -> None (stare pliki bez pola / rekoreczna edycja)
    data["monitor"] = "abc"
    restored, _ = load_program_dict(data)
    assert restored.monitor is None
    data["monitor"] = ""
    restored, _ = load_program_dict(data)
    assert restored.monitor is None


def test_serializer_block_monitor_param_survives():
    """Parametr 'monitor' bloku przechodzi przez filtrespecu ParamSpec."""
    program = Program(name="x")
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params["monitor"] = 2
    program.set_socket(start.id, "next", click.id)
    data = program_to_dict(program)
    restored, _ = load_program_dict(data)
    rb = next(b for b in restored.blocks.values() if b.type == "click")
    assert rb.params["monitor"] == 2


# ------------------------------------------------- podglad ukladu (skalowanie)
def test_scale_layout_three_monitors_negative_y():
    from snapclick.gui.monitor_layout import scale_layout
    items, scale = scale_layout(MONITORS, 640, 300, margin=10)
    assert len(items) == 3 and scale > 0
    by_idx = {it.index: it for it in items}
    # caly uklad miesci sie w okienku (z marginesem)
    for it in items:
        x, y, w, h = it.rect
        assert 10 - 1e-6 <= x and 10 - 1e-6 <= y
        assert x + w <= 640 - 10 + 1e-6 and y + h <= 300 - 10 + 1e-6
    # proporcje zachowane: 1280x512 -> ten sam scale dla kazdego monitora
    assert abs(by_idx[1].rect[2] - 640 * scale) < 1e-6
    assert abs(by_idx[3].rect[3] - 256 * scale) < 1e-6
    # wzgledne polozenie: gorny monitor (ujemne Y) jest NA GORZE mapy,
    # a poziomo miedzy dolnymi (x m1 < x m3 < x m2)
    assert by_idx[3].rect[1] < by_idx[1].rect[1]
    assert by_idx[1].rect[1] == by_idx[2].rect[1]
    assert by_idx[1].rect[0] < by_idx[3].rect[0] < by_idx[2].rect[0]
    # styk prawej krawedzi m1 z lewa m2 (skala liniowa, zero luk)
    x1, _, w1, _ = by_idx[1].rect
    x2 = by_idx[2].rect[0]
    assert abs(x1 + w1 - x2) < 1e-6


def test_scale_layout_edge_cases():
    from snapclick.gui.monitor_layout import scale_layout
    items, scale = scale_layout([], 500, 400)
    assert items == [] and scale == 1.0
    items, _ = scale_layout(MONITORS, 0, 300)   # okienko zerowe -> pusto
    assert items == []


@pytest.fixture()
def qapp_instance():
    """QApplication dla testu dialogu (pominiecie gdy brak QPA — jak smoke)."""
    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 wymagany")
    from PySide6.QtWidgets import QApplication
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # pragma: no cover - CI bez wyswietlacza
        pytest.skip(f"QApplication niedostepny: {exc}")
    yield app


def test_monitor_layout_dialog_builds_and_selects(qapp_instance):
    """Dialog sklada sie i emituje wybor monitora (sciezka dwukliku)."""
    from snapclick.gui.monitor_layout import MonitorLayoutDialog
    dlg = MonitorLayoutDialog(lambda: list(MONITORS), current=3)
    chosen = []
    dlg.monitor_chosen.connect(chosen.append)
    dlg.view.resize(520, 300)
    dlg.view._relayout()
    assert len(dlg.view._items) == 3
    dlg._on_activated(3)          # sygnal view.monitor_activated trafia tutaj
    assert chosen == [3]
    dlg._choose(0)                # przycisk 'Wszystkie ekrany'
    assert chosen == [3, 0]
    dlg.deleteLater()
