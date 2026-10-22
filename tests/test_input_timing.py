"""Timing klikniec (hold przycisku) i focus okna — regresja 'gra nie reaguje'.

Sciezka Windows: natywny SendInput z REALNYM przytrzymaniem przycisku.
Sciezka X11: analogiczny schemat przez XTEST (Xlib mockowany — test
uruchamialny rowniez na Windows).
Sciezka interpretera: aktywacja okna na starcie + per-klik wg parametru.
"""
from __future__ import annotations

import sys
import types

import pytest

from snapclick.core.settings import InputSettings, set_settings
from snapclick.core.model.blocks import BlockType
from snapclick.core.model.program import Program

from conftest import FakeScreen, FakeTemplateRegistry, FakeWindows
from test_interpreter import BUTTON, make_scene  # scena i szablon wspoldzielone


@pytest.fixture()
def fast_settings():
    """Znane timingi bez zapisu na dysk; przywrocenie po tescie."""
    from snapclick.core import settings as S
    prev = S._current
    set_settings(InputSettings(mouse_hold_s=0.12, move_settle_s=0.05,
                               double_gap_s=0.07, release_settle_s=0.03,
                               focus_delay_s=0.10),
                 persist=False)
    yield S.get_settings()
    S._current = prev


# --------------------------------------------------------------------- win32
@pytest.mark.skipif(sys.platform != "win32", reason="SendInput tylko Windows")
def test_win32_click_uses_real_button_hold(fast_settings, monkeypatch):
    import snapclick.core.platform.win32 as w32

    log = []
    monkeypatch.setattr(w32, "win_move_abs",
                        lambda x, y: log.append(("move", x, y)))
    monkeypatch.setattr(w32, "win_button",
                        lambda b, down: log.append(("button", b, down)))
    monkeypatch.setattr(w32.time, "sleep", lambda s: log.append(("sleep", s)))

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend.click(640, 480, button="right")

    assert log == [("move", 640, 480),
                   ("sleep", 0.05),
                   ("button", "right", True),
                   ("sleep", 0.12),          # ← przytrzymanie (przedtem 0 ms)
                   ("button", "right", False),
                   ("sleep", 0.03)]


@pytest.mark.skipif(sys.platform != "win32", reason="SendInput tylko Windows")
def test_win32_click_double_has_gap_between_pairs(fast_settings, monkeypatch):
    import snapclick.core.platform.win32 as w32

    log = []
    monkeypatch.setattr(w32, "win_move_abs", lambda x, y: None)
    monkeypatch.setattr(w32, "win_button",
                        lambda b, down: log.append(("button", b, down)))
    monkeypatch.setattr(w32.time, "sleep", lambda s: log.append(("sleep", s)))

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend.click(1, 2, button="left", double=True)

    presses = [e for e in log if e[0] == "button" and e[2]]
    releases = [e for e in log if e[0] == "button" and not e[2]]
    assert len(presses) == len(releases) == 2
    assert ("sleep", 0.07) in log            # gap miedzy parami


# ---------------------------------------------------- klik PostMessage (Win)
@pytest.mark.skipif(sys.platform != "win32", reason="PostMessage tylko Windows")
def test_win32_click_postmessage_routes_to_hwnd(fast_settings, monkeypatch):
    """click_method='postmessage' -> WM_*BUTTONDOWN/UP do HWND pod punktem."""
    from snapclick.core.settings import set_settings

    set_settings(InputSettings(click_method="postmessage", mouse_hold_s=0.12,
                               move_settle_s=0.0, release_settle_s=0.0),
                 persist=False)
    import snapclick.core.platform.win32 as w32

    msgs = []
    monkeypatch.setattr(w32, "win_move_abs", lambda x, y: None)
    monkeypatch.setattr(w32, "win_window_at_point", lambda x, y: 0xABCD)
    monkeypatch.setattr(w32, "win_screen_to_client",
                        lambda hwnd, x, y: (x - 10, y - 20))
    monkeypatch.setattr(
        w32, "win_post_message",
        lambda hwnd, msg, wp, x, y: msgs.append((hwnd, hex(msg), wp, x, y)))
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = None
    backend.click(110, 120, button="left")

    assert msgs[0] == (0xABCD, "0x200", 0, 100, 100)          # MOUSEMOVE
    assert msgs[1] == (0xABCD, "0x201", 1, 100, 100)          # LBUTTONDOWN
    assert msgs[2] == (0xABCD, "0x202", 0, 100, 100)          # LBUTTONUP


@pytest.mark.skipif(sys.platform != "win32", reason="PostMessage tylko Windows")
def test_win32_click_postmessage_fallback_target_hwnd(fast_settings,
                                                      monkeypatch):
    """Gdy WindowFromPoint zwraca 0, klik trafia do HWND okna z programu."""
    from snapclick.core.settings import set_settings

    set_settings(InputSettings(click_method="postmessage", mouse_hold_s=0.0,
                               move_settle_s=0.0, release_settle_s=0.0),
                 persist=False)
    import snapclick.core.platform.win32 as w32

    calls = []
    monkeypatch.setattr(w32, "win_move_abs", lambda x, y: None)
    monkeypatch.setattr(w32, "win_window_at_point", lambda x, y: 0)
    monkeypatch.setattr(w32, "win_screen_to_client", lambda hwnd, x, y: (x, y))
    monkeypatch.setattr(
        w32, "win_post_message",
        lambda hwnd, msg, wp, x, y: calls.append((hwnd, msg)))
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = 0x1234
    backend.click(5, 5, button="right")

    assert {hwnd for hwnd, _ in calls} == {0x1234}
    msgs = [m for _, m in calls]
    assert w32._WM_MOUSEMOVE in msgs
    assert w32._WM_RBUTTONDOWN in msgs and w32._WM_RBUTTONUP in msgs


@pytest.mark.skipif(sys.platform != "win32", reason="PostMessage tylko Windows")
def test_win32_click_postmessage_without_window_raises(fast_settings,
                                                       monkeypatch):
    from snapclick.core.settings import set_settings
    from snapclick.core.platform.base import BackendError

    set_settings(InputSettings(click_method="postmessage"), persist=False)
    import snapclick.core.platform.win32 as w32

    monkeypatch.setattr(w32, "win_move_abs", lambda x, y: None)
    monkeypatch.setattr(w32, "win_window_at_point", lambda x, y: 0)
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = None
    with pytest.raises(BackendError):
        backend.click(5, 5)
    monkeypatch.setattr(w32, "win_move_abs", lambda x, y: None)  # porzadek


# ----------------------------------------------------------------------- x11
class FakeXDisplay:
    def sync(self):
        pass

    def flush(self):
        pass


@pytest.fixture()
def x11_click_backend(monkeypatch):
    """Backend X11 z podstawionym XTEST (Xlib nie jest zainstalowany na Win)."""
    calls = []
    xtest = types.ModuleType("Xlib.ext.xtest")

    def fake_input(display, req_type, detail=0, x=0, y=0):
        calls.append((req_type, detail, x, y))

    xtest.fake_input = fake_input
    ext = types.ModuleType("Xlib.ext")
    ext.xtest = xtest
    xlib = types.ModuleType("Xlib")
    monkeypatch.setitem(sys.modules, "Xlib", xlib)
    monkeypatch.setitem(sys.modules, "Xlib.ext", ext)
    monkeypatch.setitem(sys.modules, "Xlib.ext.xtest", xtest)

    import snapclick.core.platform.x11 as x11
    monkeypatch.setattr(x11.time, "sleep", lambda s: calls.append(("sleep", s)))

    backend = x11.X11InputBackend.__new__(x11.X11InputBackend)
    backend._display = FakeXDisplay()
    backend._clip_tool = None
    return backend, calls


def test_x11_click_press_release_have_hold(x11_click_backend, fast_settings):
    backend, calls = x11_click_backend
    backend.click(300, 200, button="left")

    # BUTTON_PRESS (4) i BUTTON_RELEASE (5) z przytrzymaniem pomiedzy
    ev = [c for c in calls if not isinstance(c[0], str)]
    kinds = [c[0] for c in ev]
    assert kinds == [6, 4, 5]                 # motion, press, release
    sleeps = [c[1] for c in calls if isinstance(c[0], str)]
    assert 0.12 in sleeps                     # hold > 0 ms
    assert ev[1][1] == 1                      # przycisk 1 = lewy


def test_x11_key_press_release_have_hold(x11_click_backend, fast_settings):
    """Regresja cichego gubienia klawiszy: KeyPress i KeyRelease musza byc
    przedzielone key_hold_s (aplikacje pollujace XQueryKeymap nie widza
    impulsu 0 ms)."""
    backend, calls = x11_click_backend
    backend._send_keycode(30)
    kinds = [c[0] for c in calls]
    assert kinds == [4, "sleep", 5]            # press -> hold -> release
    assert calls[1][1] == pytest.approx(0.012)  # domyslny key_hold_s


def test_x11_click_double_sends_two_pairs(x11_click_backend, fast_settings):
    backend, calls = x11_click_backend
    backend.click(0, 0, button="right", double=True)
    presses = [c for c in calls
               if not isinstance(c[0], str) and c[0] == 4]
    assert len(presses) == 2
    assert all(c[1] == 3 for c in presses)    # przycisk 3 = prawy


# --------------------------------------------------------------- interpreter
class RecordingWindows(FakeWindows):
    def __init__(self):
        super().__init__()
        self.activated: list[str] = []

    def activate(self, title_substr):
        self.activated.append(title_substr)
        return True


def build_focus_interp(window: RecordingWindows):
    from snapclick.core.engine.events import EventBus
    from snapclick.core.engine.interpreter import Interpreter

    class _In:
        def __init__(self):
            self.actions = []

        def move(self, x, y): self.actions.append(("move", x, y))
        def click(self, x, y, button="left", double=False):
            self.actions.append(("click", x, y))
        def press_combo(self, combo): pass
        def type_text(self, text, method="auto"): pass
        def set_clipboard(self, text): pass

    program = Program(name="focus-test", window_title="MyApp")
    registry = FakeTemplateRegistry({"button": BUTTON})
    screen = FakeScreen(lambda region: make_scene(True))
    inp = _In()
    interp = Interpreter(program, registry, screen, inp, window, EventBus())
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params["template"] = "button"
    click.params["timeout"] = 0.1
    click.params["post_wait"] = 0.0
    program.set_socket(start.id, "next", click.id)
    return program, interp, inp


def build_type_interp(window: RecordingWindows, inp=None):
    from snapclick.core.engine.events import EventBus
    from snapclick.core.engine.interpreter import Interpreter

    class _In:
        def type_text(self, text, method="auto"):
            self.typed.append((text, method))
        def __init__(self):
            self.typed = []

    program = Program(name="type-test", window_title="MyApp")
    registry = FakeTemplateRegistry({})
    screen = FakeScreen(lambda region: make_scene(True))
    inp = inp or _In()
    interp = Interpreter(program, registry, screen, inp, window, EventBus())
    start = program.add_block(BlockType.START)
    tt = program.add_block(BlockType.TYPE_TEXT)
    tt.params["text"] = "hello"
    program.set_socket(start.id, "next", tt.id)
    return program, interp, inp


def test_type_text_reactivates_window_before_typing(fast_settings):
    """Klawiatura trafia do okna z focusem — przed pisaniem focus musi byc
    odzyskany (regresja: tekst 'znikal' gdy overlay sciagnal focus w trakcie
    przebiegu)."""
    win = RecordingWindows()
    _prog, interp, inp = build_type_interp(win)
    assert interp.run() == "ok"
    assert inp.typed == [("hello", "auto")]
    assert win.activated == ["MyApp", "MyApp"]   # start + tuż przed pisaniem


def test_type_text_logs_clipboard_fallback(fast_settings):
    """'auto' bez xclip/xsel po cichu wpada na XTEST — log MUSI to zglosic."""
    from snapclick.core.engine.events import EventKind

    class _NoClip:
        def __init__(self):
            self.typed = []

        def clipboard_available(self):
            return False

        def type_text(self, text, method="auto"):
            self.typed.append((text, method))

    win = RecordingWindows()
    _prog, interp, inp = build_type_interp(win, inp=_NoClip())
    seen = []
    interp.events.subscribe(lambda e: seen.append(e))
    assert interp.run() == "ok"
    logs = [e.message for e in seen if e.kind is EventKind.LOG]
    assert any("Schowek" in m or "clipboard" in m.lower() for m in logs), logs


def test_run_activates_window_at_start(fast_settings):
    win = RecordingWindows()
    _prog, interp, _inp = build_focus_interp(win)
    assert interp.run() == "ok"
    assert win.activated == ["MyApp"]        # raz, przed pierwszym klikiem


def test_focus_disabled_skips_activation(fast_settings, monkeypatch):
    monkeypatch.setattr("snapclick.core.engine.interpreter.get_settings",
                        lambda: InputSettings(focus_enabled=False))
    win = RecordingWindows()
    _prog, interp, _inp = build_focus_interp(win)
    interp.run()
    assert win.activated == []


def test_focus_param_on_forces_per_click(fast_settings, monkeypatch):
    """focus='on' nadpisuje regule globalna (domyslnie wylaczona)."""
    win = RecordingWindows()
    program, interp, _inp = build_focus_interp(win)
    program.get(list(program.blocks)[-1]).params["focus"] = "on"
    interp.run()
    assert win.activated == ["MyApp", "MyApp"]   # start + klik


def test_focus_param_off_suppresses_global_after_click(fast_settings,
                                                       monkeypatch):
    monkeypatch.setattr("snapclick.core.engine.interpreter.get_settings",
                        lambda: InputSettings(focus_after_click=True))
    win = RecordingWindows()
    program, interp, _inp = build_focus_interp(win)
    program.get(list(program.blocks)[-1]).params["focus"] = "off"
    interp.run()
    assert win.activated == ["MyApp"]        # tylko start


def test_focus_exception_does_not_abort_run(fast_settings):
    """Awaria aktywacji (antybot/UPPI) nie moze wywrócic calego przebiegu."""
    class ExplodingWindows(RecordingWindows):
        def activate(self, title_substr):
            raise RuntimeError("foreground denied")

    win = ExplodingWindows()
    _prog, interp, inp = build_focus_interp(win)
    assert interp.run() == "ok"
    assert any(a[0] == "click" for a in inp.actions)


def test_hwnd_handed_to_input_for_postmessage(fast_settings):
    """Interpreter podaje backendowi HWND okna (fallback klików PostMessage)."""
    class HwndWindows(RecordingWindows):
        def find_hwnd(self, title_substr):
            return 0xFEED

    class TargetInput:
        def __init__(self):
            self.actions = []
            self.target = None

        def set_target_window(self, window_id): self.target = window_id
        def move(self, x, y): pass
        def click(self, x, y, button="left", double=False):
            self.actions.append(("click", x, y))
        def press_combo(self, combo): pass
        def type_text(self, text, method="auto"): pass
        def set_clipboard(self, text): pass

    win = HwndWindows()
    inp = TargetInput()
    from snapclick.core.engine.events import EventBus
    from snapclick.core.engine.interpreter import Interpreter

    program = Program(name="hwnd-test", window_title="MyApp")
    registry = FakeTemplateRegistry({"button": BUTTON})
    screen = FakeScreen(lambda region: make_scene(True))
    interp = Interpreter(program, registry, screen, inp, win, EventBus())
    start = program.add_block(BlockType.START)
    click = program.add_block(BlockType.CLICK)
    click.params["template"] = "button"
    click.params["timeout"] = 0.1
    click.params["post_wait"] = 0.0
    program.set_socket(start.id, "next", click.id)

    assert interp.run() == "ok"
    assert inp.target == 0xFEED


# ------------------------------------------------- focus bez sygnatur ALT
@pytest.mark.skipif(sys.platform != "win32", reason="user32 tylko Windows")
def test_bring_to_front_no_alt_trick_and_no_restore(fast_settings, monkeypatch):
    """keybd_event(VK_MENU) to sygnatura ResetInputState — antybot blokuje
    wtedy CALY input. SW_RESTORE zdejmuje maksymalizacje borderless."""
    import ctypes.wintypes as wintypes

    import snapclick.core.platform.win32 as w32

    calls = []
    u32 = w32._user32
    monkeypatch.setattr(u32, "IsIconic", lambda h: False)
    monkeypatch.setattr(u32, "SetForegroundWindow",
                        lambda h: calls.append("setfg") or False)
    monkeypatch.setattr(u32, "GetForegroundWindow", lambda: 0)
    monkeypatch.setattr(u32, "ShowWindow",
                        lambda h, cmd: calls.append(("show", cmd)))
    monkeypatch.setattr(u32, "keybd_event",
                        lambda *a: calls.append(("keybd", a)))
    monkeypatch.setattr(u32, "SystemParametersInfoW",
                        lambda *a: True)

    w32.bring_to_front(wintypes.HWND(0x42))
    assert not any(kind == "keybd" for kind, *_ in calls
                   if isinstance(kind, str))          # zadnego ALT
    assert ("show", 9) not in calls                    # brak RESTORE okna
    monkeypatch.undo()


def test_settings_roundtrip_click_method(tmp_path, monkeypatch):
    """click_method (str) przezywa zapis/odczyt settings.json."""
    from snapclick.core import settings as S
    from pathlib import Path

    monkeypatch.setattr(S, "settings_path", lambda: tmp_path / "settings.json")
    S.set_settings(InputSettings(click_method="postmessage",
                                 mouse_hold_s=0.1))
    loaded = S.load_input_settings()
    assert loaded.click_method == "postmessage"
    assert loaded.mouse_hold_s == 0.1


# ---------------------------------------- wpisywanie WM_CHAR (antybot, Win)
def test_win_char_wparam_ascii_and_cp1250():
    """Okno gry jest ANSI/cp1250 — 'ł' musi miec wParam 0xB3, nie 0x142."""
    import sys as _sys
    if _sys.platform != "win32":
        import pytest as _p
        _p.skip("win32 only")
    import snapclick.core.platform.win32 as w32

    assert w32.win_char_wparam("Z") == ord("Z")
    assert w32.win_char_wparam("ł") == 0xB3       # cp1250 lower ł
    assert w32.win_char_wparam("Ł") == 0xA3       # cp1250 upper Ł
    assert w32.win_char_wparam("ś") == 0x9C
    assert w32.win_char_wparam("€") == 0x80       # EURO jest w cp1250


def test_win_char_wparam_non_cp1250_falls_back_to_codepoint():
    if sys.platform != "win32":
        pytest.skip("win32 only")
    import snapclick.core.platform.win32 as w32

    assert w32.win_char_wparam("£") == ord("£")   # brak w cp1250 -> Unicode


@pytest.mark.skipif(sys.platform != "win32", reason="WM_CHAR tylko Windows")
def test_type_text_postmessage_sends_keydown_char_keyup(fast_settings,
                                                        monkeypatch):
    """Metoda 'postmessage' -> KEYDOWN/CHAR/KEYUP na znak (jak ControlSend).

    Pola czytajace wylacznie WM_KEYDOWN (klienty gier) dostaja VK; bez
    mapowania VK (obcy uklad) zostaje sam WM_CHAR. VkKeyScanW mockowany —
    wynik zalezy od ukladu klawiatury maszyny testowej.
    """
    import snapclick.core.platform.win32 as w32

    vk_map = {"Z": 0x5A, "a": 0x41, "ż": -1}
    monkeypatch.setattr(w32._user32, "VkKeyScanW",
                        lambda ch: vk_map.get(ch, -1))

    def fake_post(h, m, wp, lp):
        val = lambda c: getattr(c, "value", c)
        msgs.append((val(m), val(wp)))
        return 1

    msgs = []
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)
    monkeypatch.setattr(w32._user32, "PostMessageW", fake_post)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = 0x999
    backend._pdid = None                       # nie uzywana w tej sciezce
    backend.type_text("Zaż", method="postmessage")

    assert msgs == [
        (w32._WM_KEYDOWN, 0x5A), (w32._WM_CHAR, ord("Z")),
        (w32._WM_KEYUP, 0x5A),
        (w32._WM_KEYDOWN, 0x41), (w32._WM_CHAR, ord("a")),
        (w32._WM_KEYUP, 0x41),
        (w32._WM_CHAR, 0xBF),                   # ż bez VK -> goly WM_CHAR
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="WM_CHAR tylko Windows")
def test_type_text_auto_follows_type_method_not_click(fast_settings,
                                                      monkeypatch):
    """auto czyta type_method (NIEZALEZNE od click_method — użytkownik tak ma:
    klik SendInput + tekst PostMessage)."""
    from snapclick.core.settings import set_settings
    set_settings(InputSettings(click_method="sendinput",
                               type_method="postmessage"), persist=False)
    import snapclick.core.platform.win32 as w32

    monkeypatch.setattr(w32._user32, "VkKeyScanW", lambda ch: -1)

    def fake_post(h, m, wp, lp):
        chars.append(getattr(wp, "value", wp))
        return 1

    chars = []
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)
    monkeypatch.setattr(w32._user32, "PostMessageW", fake_post)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = 0x1
    backend._pdid = None
    backend.type_text("ab", method="auto")
    assert chars == [ord("a"), ord("b")]


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 tylko Windows")
def test_type_text_sendinput_needs_no_window(fast_settings, monkeypatch):
    """type_method='sendinput' -> SendInput Unicode, bez HWND i bez okna gry."""
    from snapclick.core.settings import set_settings
    set_settings(InputSettings(type_method="sendinput"), persist=False)
    import snapclick.core.platform.win32 as w32

    typed = []
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)
    monkeypatch.setattr(w32, "win_type_char", typed.append)
    monkeypatch.setattr(w32._user32, "GetForegroundWindow", lambda: 0)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = None
    backend._pdid = None
    backend.type_text("xyz", method="auto")    # zero wyjatku mimo braku okna
    assert typed == ["x", "y", "z"]


@pytest.mark.skipif(sys.platform != "win32", reason="WM_CHAR tylko Windows")
def test_type_text_postmessage_prefers_target_hwnd_over_foreground(
        fast_settings, monkeypatch):
    import snapclick.core.platform.win32 as w32

    def fake_post(h, m, wp, lp):
        posted.append(getattr(h, "value", h) or 0)
        return 1

    posted = []
    monkeypatch.setattr(w32.time, "sleep", lambda s: None)
    monkeypatch.setattr(w32._user32, "GetForegroundWindow", lambda: 0xDEAD)
    monkeypatch.setattr(w32._user32, "PostMessageW", fake_post)

    backend = w32.Win32InputBackend.__new__(w32.Win32InputBackend)
    backend._target_hwnd = 0x2222
    backend._pdid = None
    backend.type_text("x", method="postmessage")
    assert posted and set(posted) == {0x2222}  # wszystkie 3 komunikaty do
    # target HWND, zadny do 'przypadkowego' foreground 0xDEAD


def test_settings_invalid_click_method_falls_back(tmp_path, monkeypatch):
    import json
    from snapclick.core import settings as S

    (tmp_path / "settings.json").write_text(
        json.dumps({"input": {"click_method": "teleportacja"}}),
        encoding="utf-8")
    monkeypatch.setattr(S, "settings_path", lambda: tmp_path / "settings.json")
    assert S.load_input_settings().click_method == "sendinput"
