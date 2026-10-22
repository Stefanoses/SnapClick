"""Regresja: wpisywanie polskich znakow (metoda 'type').

Stara implementacja na Windows uzyla pydirectinput.write() z mapa ASCII i po
cichu pomijala znaki takie jak 't' z ogonkiem; na X11 znaki bez keycode'u w
ukladzie klawiatury byly pomijane przez 'continue'. Teraz:
- Windows: SendInput + KEYEVENTF_UNICODE (pelny UTF-16),
- X11: tymczasowy remap wolnego keycode'u na keysym znaku (jak xdotool).
"""
from __future__ import annotations

import sys
import types

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
    """Minimalna atrapa Xlib Display z kontrolowana mapa klawiatury PL.

    get_keyboard_mapping(code, count) zwraca `count` wierszy (jak prawdziwy
    Xlib) — _keymap() czyta cala tablice jednym zapytaniem.
    """

    def __init__(self):
        # keysym -> keycode (klawisze natywne ukladu)
        self.sym2code = {0x61: 0x1E,          # a
                         0x41: 0x1E,          # A — ten sam klawisz, level 2
                         0x20: 0x39,          # spacja
                         0xFF0D: 0x24,        # Return
                         0xFFE1: 50,          # Shift_L
                         0xFE03: 92}          # ISO_Level3_Shift (AltGr)
        # keycode -> keysym w levelu 1 (bez modyfikatorow)
        self.level1 = {0x1E: 0x61, 0x39: 0x20, 0x24: 0xFF0D,
                       0x27: 0x7B}            # '[' (Enter/level2 '{')
        self.changed = []
        self.syncs = 0
        # prawdziwy Xlib: Display NIE ma keyboard_mapping_range() — zakres
        # keycode'ow siedzi w display.info (atrybut protokolowy)
        self.display = types.SimpleNamespace(
            info=types.SimpleNamespace(min_keycode=8, max_keycode=135))

    def keysym_to_keycode(self, keysym):
        return self.sym2code.get(keysym, 0)

    def get_keyboard_mapping(self, code, count):
        return [[self.level1.get(c, 0), 0, 0, 0]
                for c in range(code, code + count)]

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
    backend._xdotool = None            # testy sciezki natywnej, nie xdotool
    backend.events = []
    orig_keycode = backend._send_keycode

    def spy(code):
        backend.events.append(("keycode", code))
    backend._send_keycode = spy
    # modyfikatory ida osobnymi prymitywami (sa TRZYMANE przez caly znak)
    backend._press_keycode = lambda code: backend.events.append(("press", code))
    backend._release_keycode = lambda code: backend.events.append(
        ("release", code))
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


def test_x11_mods_for_column_group2_is_altgr():
    """Regresja (Deck, Wine): 'pl' to uklad GRUPOWY — polskie znaki stoja w
    grupie 2 (indeksy 4..7), do ktorej wchodzi sie AltGr-em. Dawna logika
    patrzyla tylko w kolumny 0..3 grupy 1, wiec 'o' z ogonkiem ladowalo na
    remap — a Wine cache'uje tablice klawiatury i remapu NIE widzi (stad
    'bogosawiestwa')."""
    from snapclick.core.platform.x11 import X11InputBackend as B
    assert B._mods_for_column(0) == ()
    assert B._mods_for_column(1) == (0xFFE1,)            # Shift
    assert B._mods_for_column(2) == (0xFE03,)            # AltGr
    assert B._mods_for_column(3) == (0xFE03, 0xFFE1)     # AltGr+Shift
    assert B._mods_for_column(4) == (0xFE03,)            # grupa 2, baza
    assert B._mods_for_column(5) == (0xFE03, 0xFFE1)     # grupa 2, Shift


def test_x11_uppercase_uses_shift_not_remap(x11_backend):
    """'Z' musi isc jako Shift+keycode 'z' (natywnie), nie przez remap —
    inaczej gra pod Wine gubi wielkie litery."""
    backend, _ = x11_backend
    d = backend._display
    d.level1[0x1E] = 0x61
    d.level1_rows = None
    # kolumna 1 (Shift) tego samego klawisza = 'Z'
    orig = d.get_keyboard_mapping

    def mapping(code, count):
        rows = orig(code, count)
        if code <= 0x1E < code + count:
            rows[0x1E - code][1] = 0x5A
        return rows
    d.get_keyboard_mapping = mapping

    backend._send_char("Z")
    assert backend._display.changed == [], "Z nie moze byc remapowane"
    # Shift TRZYMANY przez caly znak: press Shift -> Z -> release Shift
    assert backend.events == [("press", 50), ("keycode", 0x1E),
                              ("release", 50)]


def test_x11_group2_char_uses_altgr_not_remap(x11_backend):
    """'ó' (keysym 0xF3) w grupie 2 ukladu 'pl' -> AltGr + keycode 'o'."""
    backend, _ = x11_backend
    d = backend._display
    orig = d.get_keyboard_mapping

    def mapping(code, count):
        # prawdziwy 'pl' ma 7 keysymow na keycode (grupy po 4) — fake
        # domyslnie zwraca 4, tutaj symulujemy pelna szerokosc
        rows = [list(r) + [0] * 3 for r in orig(code, count)]
        if code <= 0x20 < code + count:
            rows[0x20 - code][4] = 0xF3            # grupa 2, baza
        return rows
    d.get_keyboard_mapping = mapping

    backend._send_char("ó")
    assert backend._display.changed == [], "ó nie moze byc remapowane"
    assert backend.events == [("press", 92), ("keycode", 0x20),
                              ("release", 92)]     # AltGr trzymany przez znak


def test_x11_legacy_keysym_candidates():
    """Uklady legacy definiuja 'ł' jako lstroke (0x1A5), nie keysym Unicode —
    szukamy obu kandydatow."""
    pytest.importorskip("Xlib", reason="legacy keysymy przez Xlib.XK")
    from snapclick.core.platform.x11 import X11InputBackend as B
    cands = B._char_keysyms("ł")
    assert 0x01000142 in cands
    assert 0x1A5 in cands                          # XK_lstroke
    assert B._char_keysyms("a") == [0x61]


def test_x11_modifier_settle_gaps(x11_backend, monkeypatch):
    """Regresja (Metin2/Wine): 'Zsoj' zamiast 'Zwoj' — AltGr puszczony w tym
    samym momencie co znak przesaczal na nastepny klawisz. Miedzy press i
    release modyfikatora musza byc odstepy mod_settle_s."""
    from snapclick.core import settings as S
    from snapclick.core.settings import InputSettings, set_settings

    prev = S._current
    set_settings(InputSettings(mod_settle_s=0.05), persist=False)
    try:
        backend, _ = x11_backend
        d = backend._display
        orig = d.get_keyboard_mapping

        def mapping(code, count):
            rows = orig(code, count)
            if code <= 0x1E < code + count:
                rows[0x1E - code][1] = 0x5A          # kolumna Shift = 'Z'
            return rows
        d.get_keyboard_mapping = mapping

        sleeps = []
        monkeypatch.setattr("snapclick.core.platform.x11.time.sleep",
                            lambda s: sleeps.append(s))
        backend._send_char("Z")
        assert backend.events == [("press", 50), ("keycode", 0x1E),
                                  ("release", 50)]
        assert sleeps.count(0.05) == 2               # po press i po release
    finally:
        S._current = prev


def test_x11_clipboard_fallback_without_xclip(x11_backend, monkeypatch):
    """Deck/SteamOS nie ma xclip/xsel — schowek python-xlib + Ctrl+V to
    jedyna metoda omijajaca tlumaczenie klawiatury w Wine."""
    import snapclick.core.platform.x11 as x11

    backend, _ = x11_backend
    backend._clip_tool = None
    backend._xdotool = None
    combos = []
    backend.press_combo = combos.append

    pumped = []

    class FakeOwner:
        def pump(self, timeout):
            pumped.append(timeout)

        def close(self):
            pumped.append("close")

    monkeypatch.setattr(x11, "_ClipboardOwner", lambda text: FakeOwner())
    backend.type_text("Zwój błogosławieństwa", method="clipboard")
    assert combos == ["ctrl+v"]
    assert pumped == [x11._CLIPBOARD_TIMEOUT_S, "close"]


def test_x11_clipboard_error_when_selection_denied(x11_backend, monkeypatch):
    """Bez xclip i bez przejecia selekcji — czytelny blad, nie ciche milczenie."""
    from snapclick.core.platform.base import BackendError
    import snapclick.core.platform.x11 as x11

    backend, _ = x11_backend
    backend._clip_tool = None

    def boom(text):
        raise RuntimeError("no window")
    monkeypatch.setattr(x11, "_ClipboardOwner", boom)
    with pytest.raises(BackendError):
        backend.type_text("x", method="clipboard")


def test_x11_type_text_prefers_xdotool(x11_backend, monkeypatch):
    """xdotool to zloty standard — jezeli jest, 'type' idzie nim (pelne
    wsparcie ukladow grupowych, widoczne rowniez dla Wine)."""
    import snapclick.core.platform.x11 as x11

    backend, _ = x11_backend
    backend._xdotool = "/usr/bin/xdotool"
    runs = []
    monkeypatch.setattr(x11.subprocess, "run",
                        lambda cmd, **kw: runs.append((cmd, kw)))
    backend.type_text("Zwój błogosławieństwa", method="type")
    assert len(runs) == 1
    cmd, kw = runs[0]
    assert cmd[:2] == ["/usr/bin/xdotool", "type"]
    assert "--clearmodifiers" in cmd
    assert cmd[-1] == "Zwój błogosławieństwa"
    assert backend.events == []                    # bez wlasnego XTEST


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
    """Regresja: prawdziwy Xlib.Display NIE ma keyboard_mapping_range()
    (AttributeError('keyboard_mapping_range') wywralo pierwsze wpisywanie
    tekstu na X11) — zakres czytamy z display.info."""
    from snapclick.core.platform.x11 import X11InputBackend
    backend, _ = x11_backend
    d = backend._display
    assert not hasattr(d, "keyboard_mapping_range")   # jak w prawdziwym Xlib
    code = X11InputBackend._free_keycode(backend, d)
    assert code not in {kc for mod in d.get_modifier_mapping() for kc in mod}
    assert d.level1.get(code, 0) == 0          # naprawde wolny
    assert 8 <= code <= 135


def test_x11_press_combo_single_char_without_keysym_to_keysym(x11_backend,
                                                              monkeypatch):
    """Regresja: Display NIE ma keysym_to_keysym() — press_combo liczy keysym
    znaku wlasnym przelicznikiem (_keysym_of)."""
    # Xlib nie musi byc zainstalowany (Windows/CI) — press_combo importuje
    # XTEST wewnatrz funkcji
    xtest = types.ModuleType("Xlib.ext.xtest")
    xtest.fake_input = lambda d, t, detail=0, x=0, y=0: None
    ext = types.ModuleType("Xlib.ext")
    ext.xtest = xtest
    xlib = types.ModuleType("Xlib")
    xlib.X = types.SimpleNamespace(KeyPress=2, KeyRelease=3, ButtonPress=4,
                                   ButtonRelease=5, MotionNotify=6)
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
    monkeypatch.setitem(sys.modules, "Xlib.ext", ext)
    monkeypatch.setitem(sys.modules, "Xlib.ext.xtest", xtest)

    backend, _ = x11_backend
    backend._display.sym2code[0x62] = 0x30     # 'b' -> keycode
    sent = []
    backend._send_keysym = sent.append         # bez XTEST (Windows/CI)
    backend.press_combo("b")
    assert sent == [0x62]


def test_x11_list_windows_translates_origin(monkeypatch):
    """Regresja: Window.translate_coords wymaga (dst, src_x, src_y) —
    wczesniej list_windows wywolywalo translate_coords(root) i kazde
    listowanie okien konczylo sie TypeError (stad 'Window listing error'
    w logu i szukanie bez regionu okna)."""
    xlib = types.ModuleType("Xlib")
    xlib.X = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "Xlib", xlib)

    import snapclick.core.platform.x11 as x11

    class FakeGeom:
        width, height = 800, 600

    class FakeTrans:
        x, y = 100, 50

    class FakeWin:
        def get_full_property(self, atom, typ):
            if atom == "_NET_WM_NAME":
                return types.SimpleNamespace(value=b"MyApp")
            return None                        # brak stanu/ramki

        def get_wm_name(self):
            return None

        def get_geometry(self):
            return FakeGeom()

        def translate_coords(self, dst, src_x, src_y):
            assert (src_x, src_y) == (0, 0), "zla sygnature translate_coords"
            return FakeTrans()

    class FakeRoot:
        def get_full_property(self, atom, typ):
            if atom == "_NET_CLIENT_LIST":
                return types.SimpleNamespace(value=[42])
            return None

    class FakeScreenObj:
        root = FakeRoot()

    class FakeD:
        def screen(self):
            return FakeScreenObj()

        def intern_atom(self, name):
            return name

        def create_resource_object(self, kind, wid):
            assert kind == "window" and wid == 42
            return FakeWin()

    backend = x11.X11WindowBackend.__new__(x11.X11WindowBackend)
    backend._display = FakeD()
    wins = backend.list_windows()
    assert len(wins) == 1
    assert wins[0].title == "MyApp"
    assert wins[0].region == (100, 50, 800, 600)


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
