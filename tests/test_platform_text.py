"""Regresja: wpisywanie polskich znakow (metoda 'type').

Stara implementacja na Windows uzyla pydirectinput.write() z mapa ASCII i po
cichu pomijala znaki takie jak 't' z ogonkiem; na X11 znaki bez keycode'u w
ukladzie klawiatury byly pomijane przez 'continue'. Teraz:
- Windows: SendInput + KEYEVENTF_UNICODE (pelny UTF-16),
- X11: tymczasowy remap wolnego keycode'u na keysym znaku (jak xdotool).
"""
from __future__ import annotations

import sys

import pytest

POLISH = "jak złapać suma"


# --------------------------------------------------------------------- win32
@pytest.mark.skipif(sys.platform != "win32", reason="SendInput tylko Windows")
def test_unicode_units_bmp_and_surrogate():
    from snapclick.core.platform.win32 import _unicode_units
    assert _unicode_units("a") == [0x61]
    assert _unicode_units("ł") == [0x142]
    assert _unicode_units("ż") == [0x17C]
    assert _unicode_units("\U0001F600") == [0xD83D, 0xDE00]  # para surrogate


@pytest.mark.skipif(sys.platform != "win32", reason="SendInput tylko Windows")
def test_win_type_char_sends_unicode_events(monkeypatch):
    import snapclick.core.platform.win32 as w32

    sent = []
    monkeypatch.setattr(w32, "_win_send_inputs",
                        lambda events: sent.append(list(events)))

    w32.win_type_char("ł")

    assert len(sent) == 1                      # jedno spakowane cosie
    press, release = sent[0]                   # press + release
    assert press.type == w32._INPUT_KEYBOARD
    assert press.ki.wVk == 0                   # wUnicode: wVk = 0
    assert press.ki.wScan == 0x142             # kod UTF-16 znaku w wScan
    assert press.ki.dwFlags == w32._KEYEVENTF_UNICODE
    assert release.ki.wScan == 0x142
    assert release.ki.dwFlags == (w32._KEYEVENTF_UNICODE
                                  | w32._KEYEVENTF_KEYUP)


@pytest.mark.skipif(sys.platform != "win32", reason="SendInput tylko Windows")
def test_win_type_text_method_type_keeps_every_char(monkeypatch):
    """Regresja glownego buga: zadna 'ł' nie moze zniknac przy method='type'."""
    import snapclick.core.platform.win32 as w32

    typed = []
    monkeypatch.setattr(w32, "win_type_char", typed.append)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)

    class FakePdid:
        def press(self, key):
            typed.append(f"<{key}>")

    backend._pdid = FakePdid()
    backend.type_text(POLISH, method="type")
    assert "".join(typed) == POLISH            # brak pominietych znakow


# ----------------------------------------------------------------------- x11
class FakeDisplay:
    """Minimalna atrapa Xlib Display z kontrolowana mapa klawiatury PL."""

    def __init__(self):
        # keysym -> keycode (klawisze natywne ukladu)
        self.sym2code = {0x61: 0x1E,          # a
                         0x41: 0x1E,          # A — ten sam klawisz, level 2
                         0x20: 0x39,          # spacja
                         0xFF0D: 0x24}        # Return
        # keycode -> keysym w levelu 1 (bez modyfikatorow)
        self.level1 = {0x1E: 0x61, 0x39: 0x20, 0x24: 0xFF0D,
                       0x27: 0x7B}            # '[' (Enter/level2 '{')
        self.changed = []
        self.syncs = 0

    def keysym_to_keycode(self, keysym):
        return self.sym2code.get(keysym, 0)

    def get_keyboard_mapping(self, code, count):
        first = self.level1.get(code, 0)
        return [[first, 0, 0, 0]]              # 1 keysym na 4 levelow

    def keyboard_mapping_range(self):
        return (8, 135)

    def get_modifier_mapping(self):
        return [(50, 62, 0, 0, 0, 0, 0, 0)] * 8

    def change_keyboard_mapping(self, code, entries):
        self.changed.append((code, [list(e) for e in entries]))
        # symulacja serwera X: od swiezego mapowania zalezy keysym_to_keycode
        first = entries[0][0]
        old = self.level1.get(code, 0)
        if first:
            self.sym2code[first] = code
            self.level1[code] = first
        else:
            self.sym2code.pop(old, None)
            self.level1.pop(code, None)

    def sync(self):
        self.syncs += 1


@pytest.fixture()
def x11_backend():
    from snapclick.core.platform.x11 import X11InputBackend
    backend = X11InputBackend.__new__(X11InputBackend)   # bez laczenia z X
    backend._display = FakeDisplay()
    backend._clip_tool = None
    backend.events = []
    orig_keycode = backend._send_keycode

    def spy(code):
        backend.events.append(("keycode", code))
    backend._send_keycode = spy
    yield backend, orig_keycode


def test_x11_display_property_survives_strict_display(monkeypatch):
    """Regresja: Xlib.display.Display NIE ma get_error_handler() (istnieje
    tylko set_error_handler) — wlasnie to wywolanie wywrocilo pierwszy
    przebieg na X11: AttributeError('get_error_handler')."""
    import snapclick.core.platform.x11 as x11

    class StrictDisplay:
        """Dokladnie jak prawdziwy Display: zadnych atrybutow ponizej."""
        def sync(self):
            pass

    class FakeXlibModule:
        Display = StrictDisplay

    monkeypatch.setattr(x11, "_xlib", lambda: FakeXlibModule)
    backend = x11.X11InputBackend.__new__(x11.X11InputBackend)
    backend._display = None
    d = backend.display
    assert isinstance(d, StrictDisplay)
    assert backend.display is d      # polaczenie cache'owane


def test_x11_keysym_mapping_rules():
    from snapclick.core.platform.x11 import X11InputBackend
    f = X11InputBackend._keysym_of
    assert f("a") == 0x61          # ASCII 1:1
    assert f("ł") == 0x01000142    # Unicode keysym = 0x01000000 + codepoint
    assert f("ß") == 0xDF          # Latin-1 bez prefiksu Unicode


def test_x11_native_path_for_plain_keysym(x11_backend):
    backend, _ = x11_backend
    backend._send_char("a")
    assert backend.events == [("keycode", 0x1E)]
    assert backend._display.changed == []      # bez remapowania


def test_x11_shifted_char_uses_remap_not_plain_key(x11_backend):
    """'A' ma keycode klawisza 'a' — wciśniecie go bez Shift daloby 'a'."""
    backend, _ = x11_backend
    backend._send_char("A")
    pressed = [code for kind, code in backend.events]
    assert backend._display.changed, "powinien byc remap"
    assert pressed and pressed[0] != 0x1E, "nie moze wcisnac klawisza 'a'"
    # przywrocone oryginalne mapowanie
    assert backend._display.changed[-1][1] == [[0, 0, 0, 0]]


def test_x11_missing_char_uses_remap(x11_backend):
    backend, _ = x11_backend
    backend._send_char("ł")                    # keysym 0x01000142 bez keycode'u
    remaps = backend._display.changed
    assert len(remaps) == 2                    # wstawienie + przywrocenie
    assert remaps[0][1] == [[0x01000142, 0, 0, 0]]
    assert remaps[1][1] == [[0, 0, 0, 0]]      # original (kod byl wolny)
    # wcisniety zostal kod tymczasowo zmapowany
    assert backend.events[-1] == ("keycode", remaps[0][0])


def test_x11_remap_restores_mapping_on_error(x11_backend):
    backend, _ = x11_backend

    def boom(code):
        raise RuntimeError("XTEST padl")
    backend._send_keycode = boom
    with pytest.raises(RuntimeError):
        backend._send_char("ł")
    # mapping musi byc przywrocony nawet przy wyjtku
    assert backend._display.changed[-1][1] == [[0, 0, 0, 0]]


def test_x11_free_keycode_skips_reserved(x11_backend):
    from snapclick.core.platform.x11 import X11InputBackend
    backend, _ = x11_backend
    d = backend._display
    code = X11InputBackend._free_keycode(backend, d)
    assert code not in {kc for mod in d.get_modifier_mapping() for kc in mod}
    assert d.level1.get(code, 0) == 0          # naprawde wolny


def test_x11_type_text_keeps_every_polish_char(x11_backend):
    """Regresja glownego buga: 'type_text' nie moze gubic zadnego znaku."""
    backend, _ = x11_backend
    d = backend._display
    seen = []
    orig = backend._send_keycode

    def spy(code):
        # odczyt z mapowania serwera — dokladnie to, co dostanie aplikacja
        sym = d.level1[code]
        if sym >= 0x01000000:                  # keysym Unicode -> codepoint
            seen.append(chr(sym - 0x01000000))
        else:
            seen.append(chr(sym))
    backend._send_keycode = spy
    backend.type_text(POLISH, method="type")
    assert "".join(seen) == POLISH
    # kazdy remap przywrocony do origianlu
    for _code, entries in d.changed[1::2]:
        assert entries[0][0] in (0, )
