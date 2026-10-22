"""Backend platformy Linux (sesja X11).

- Input: python-xlib rozszerzenie XTEST (natywne wstrzykiwanie zdarzeń).
- Okny: właściwości EWMH na oknie głównym (_NET_CLIENT_LIST + _NET_FRAME_EXTENTS).
- Schowek: `xclip` lub `xsel` (dostępne w większości dystrybucji);
  bez nich `type_text(method='clipboard')` zgłosi czytelny błąd.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import List, Optional

from ..settings import get_settings
from .base import BackendError, Region, WindowInfo


def _xlib():
    try:
        from Xlib import X, display, error  # noqa: F401
        from Xlib.ext import xtest
        from Xlib.protocol import event  # noqa: F401
    except ImportError as exc:  # pragma: no cover - testowalne przez moki
        raise BackendError(
            "Brak pakietu python-xlib (pip install python-xlib)."
        ) from exc
    return display


def _keycode_range(d):
    """Zakres keycode'ow serwera X.

    Uwaga: Xlib.display.Display NIE ma metody keyboard_mapping_range() —
    wartosci z protokolu X leza w display.info (regresja:
    AttributeError('keyboard_mapping_range') przy wpisywaniu tekstu).
    """
    info = getattr(getattr(d, "display", None), "info", None)
    lo = int(getattr(info, "min_keycode", 0) or 8)
    hi = int(getattr(info, "max_keycode", 0) or 255)
    return lo, hi


class _X11Common:
    """Wspólne połączenie z serwerem X (jedno na backend, wątek roboczy)."""

    def __init__(self) -> None:
        self._display = None

    @property
    def display(self):
        # Uwaga: Xlib.display.Display NIE ma metody get_error_handler()
        # (istnieje tylko set_error_handler) — dawne sprawdzenie tutaj rzucalo
        # AttributeError('get_error_handler') przy pierwszym uzyciu backendu.
        if self._display is None:
            disp = _xlib()
            try:
                self._display = disp.Display()
            except Exception as exc:  # pragma: no cover
                raise BackendError(
                    f"Nie można połączyć się z serwerem X11 (DISPLAY): {exc}"
                ) from exc
        return self._display


class X11InputBackend(_X11Common):
    """Mysz i klawiatura przez XTEST + klawisze przez keysymy."""

    name = "x11-xtest"

    def __init__(self) -> None:
        super().__init__()
        self._clip_tool = self._detect_clipboard_tool()

    @staticmethod
    def _detect_clipboard_tool() -> Optional[str]:
        for tool in ("xclip", "xsel"):
            if shutil.which(tool):
                return tool
        return None

    # -------------------------------------------------------------- mouse
    def move(self, x: int, y: int) -> None:
        from Xlib.ext import xtest
        d = self.display
        xtest.fake_input(d, 6, 0, x=int(x), y=int(y))  # MotionNotify
        d.sync()

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        """Ruch -> settle -> Press -> HOLD -> Release (per XTEST).

        Bez przytrzymania klienci odpytujący stan przycisku (gry przez
        XQueryPointer/Zephyr-style polling) moga nie zdazyc zobaczyc
        przycisnietego stanu miedzy dwoma fake_input().
        """
        from Xlib.ext import xtest
        d = self.display
        btn = {"left": 1, "middle": 2, "right": 3}.get(button, 1)
        st = get_settings()
        self.move(x, y)
        d.sync()
        if st.move_settle_s > 0:
            time.sleep(st.move_settle_s)
        n = 2 if double else 1
        for i in range(n):
            xtest.fake_input(d, 4, btn)   # ButtonPress
            d.sync()
            if st.mouse_hold_s > 0:
                time.sleep(st.mouse_hold_s)
            xtest.fake_input(d, 5, btn)   # ButtonRelease
            d.sync()
            if i < n - 1 and st.double_gap_s > 0:
                time.sleep(st.double_gap_s)
        if st.release_settle_s > 0:
            time.sleep(st.release_settle_s)

    # ---------------------------------------------------------- keyboard
    def _send_keysym(self, keysym: int) -> None:
        from Xlib.ext import xtest
        d = self.display
        keycode = d.keysym_to_keycode(keysym)
        if keycode == 0:
            raise BackendError(f"Brak keysymu na tej klawiaturze: {keysym:#x}")
        xtest.fake_input(d, 4, keycode)
        xtest.fake_input(d, 5, keycode)
        d.sync()

    _MOD_MAP = {  # nazwa -> (keysym modu, bitmaska)
        "ctrl": (0xFFE3, 4), "control": (0xFFE3, 4),
        "alt": (0xFFE9, 8), "shift": (0xFFE1, 1),
        "win": (0xFFEB, 0x40), "super": (0xFFEB, 0x40),
    }

    def press_combo(self, combo: str) -> None:
        from Xlib.ext import xtest
        d = self.display
        parts = [p.strip().lower() for p in combo.replace("+", ",").split(",") if p.strip()]
        if not parts:
            raise BackendError(f"Pusto zdefiniowane combo klawiszy: {combo!r}")
        mods, main = [], parts[-1]
        for p in parts[:-1]:
            if p in self._MOD_MAP:
                mods.append(self._MOD_MAP[p][0])
            else:
                raise BackendError(f"Nieznany modyfikator: {p}")
        for ks in mods:
            xtest.fake_input(d, 4, d.keysym_to_keycode(ks))
        main_key = {"enter": 0xFF0D, "esc": 0xFF1B, "space": 0xFF20,
                    "tab": 0xFF09, "backspace": 0xFF08, "delete": 0xFFFF,
                    "del": 0xFFFF}.get(main)
        if main_key is None and len(main) == 1:
            # Display NIE ma keysym_to_keysym(); keysym znaku liczony jak
            # w _keysym_of (Latin-1 1:1, reszta z prefiksem Unicode)
            main_key = self._keysym_of(main)
        if main_key is None or d.keysym_to_keycode(main_key) == 0:
            # zwolnij trzymane modyfikatory przed rzuceniem błędu
            for ks in mods:
                xtest.fake_input(d, 5, d.keysym_to_keycode(ks))
            d.sync()
            raise BackendError(f"Nieznany klawisz: {main}")
        self._send_keysym(main_key)
        for ks in reversed(mods):
            xtest.fake_input(d, 5, d.keysym_to_keycode(ks))
        d.sync()

    # --------------------------------------------------------- wpisywanie
    @staticmethod
    def _keysym_of(ch: str) -> int:
        """Keysym X11 dla znaku (Latin-1 1:1, reszta przez keysym Unicode)."""
        cp = ord(ch)
        return cp if cp < 0x100 else 0x01000000 + cp

    _NAMED_KEYS = {"\n": 0xFF0D, "\r": 0xFF0D, "\t": 0xFF09}

    def type_text(self, text: str, method: str = "auto") -> None:
        # Normalizacja z globalnym type_method: na X11 "sendinput" i
        # "postmessage" oznaczaja to samo (XTEST / keysymy — tu nie ma hooka
        # "injected"), "clipboard" pozostaje osobna sciezka.
        if method == "auto":
            method = get_settings().type_method
        if method in ("sendinput", "postmessage"):
            method = "type"
        if method in ("auto", "clipboard"):
            if self._clip_tool is not None:
                self.set_clipboard(text)
                self.press_combo("ctrl+v")
                return
            if method == "clipboard":
                raise BackendError(
                    "Brak narzędzia xclip/xsel — schowek niedostępny. "
                    "Zainstaluj xclip lub użyj method='type'."
                )
        # Metoda "type": kazdy znak musi trafic do celu. Wczesniej znaki bez
        # keycode'u w biezacym ukladzie byly po cichu pomijane (stad "znikajace"
        # polskie znaki); teraz nadpisujemy tymczasowo wolny keycode (xdotool).
        d = self.display
        for ch in text:
            if ch in self._NAMED_KEYS:
                self._send_keysym(self._NAMED_KEYS[ch])
                continue
            self._send_char(ch)
            time.sleep(0.01)
        d.sync()

    def _send_char(self, ch: str) -> None:
        """Wciska klawisz produkujacy znak — natywnie lub przez remap."""
        d = self.display
        keysym = self._keysym_of(ch)
        code = d.keysym_to_keycode(keysym)
        # Natywnie tylko gdy keysym jest w levelu 1 (bez modyfikatorow) —
        # inaczej 'A' wcisneloby klawisz 'a' i dalo 'a', a 'ł' mogloby dac 'Ł'.
        if code:
            try:
                unshifted = d.get_keyboard_mapping(code, 1)[0][0]
            except Exception:  # pragma: no cover - bledy protokolu X
                unshifted = None
            if unshifted == keysym:
                self._send_keycode(code)
                return
        self._send_char_via_remap(d, keysym)

    def _send_keycode(self, code: int) -> None:
        from Xlib.ext import xtest
        d = self.display
        xtest.fake_input(d, 4, code)   # KeyPress
        xtest.fake_input(d, 5, code)   # KeyRelease
        d.sync()

    def _free_keycode(self, d) -> int:
        """Keycode nieuzywany przez zadny keysym ani modyfikator."""
        lo, hi = _keycode_range(d)
        reserved = {kc for mod in d.get_modifier_mapping() for kc in mod}
        for code in range(hi, max(lo, 8) - 1, -1):   # od gory — rzadziej uzywane
            if code in reserved:
                continue
            if not any(d.get_keyboard_mapping(code, 1)[0]):
                return code
        raise BackendError("Brak wolnego keycode'u do wstrzykniecia znaku.")

    def _send_char_via_remap(self, d, keysym: int) -> None:
        """Tymczasowo mapuje wolny keycode na keysym znaku i go wciska."""
        code = self._free_keycode(d)
        original = list(d.get_keyboard_mapping(code, 1)[0])
        replacement = [keysym] + [0] * max(len(original) - 1, 0)
        try:
            d.change_keyboard_mapping(code, [replacement])
            d.sync()
            time.sleep(0.01)   # klienci odswiezaja tablice mapowania klawiszy
            self._send_keycode(code)
        finally:
            d.change_keyboard_mapping(code, [original])
            d.sync()

    # ----------------------------------------------------------- clipboard
    def set_clipboard(self, text: str) -> None:
        if self._clip_tool is None:
            raise BackendError(
                "Schowek na X11 wymaga zainstalowanego xclip albo xsel."
            )
        if self._clip_tool == "xclip":
            cmd = ["xclip", "-selection", "clipboard"]
        else:
            cmd = ["xsel", "--clipboard", "--input"]
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)


class X11WindowBackend(_X11Common):
    """Listowanie okien menedżera okien zgodnego z EWMH."""

    name = "x11-ewmh"

    _ANY_PROPERTY = 0  # AnyPropertyType

    def list_windows(self) -> List[WindowInfo]:
        from Xlib import X  # noqa: F401
        d = self.display
        root = d.screen().root
        # (translate_coords ponizej wymaga sygnatury (dst_window, x, y))

        def prop(win, name, atom="ATOM"):
            a = d.intern_atom(name)
            r = win.get_full_property(a, 0)
            return r.value if r is not None else None

        client_list = prop(root, "_NET_CLIENT_LIST")
        if client_list is None:
            return []

        wm_name_atom = d.intern_atom("_NET_WM_NAME")
        utf8_atom = d.intern_atom("UTF8_STRING")
        net_wm_state_hidden = d.intern_atom("_NET_WM_STATE_HIDDEN")

        results: List[WindowInfo] = []
        for wid in client_list:
            win = d.create_resource_object("window", int(wid))
            # tytuł: najpierw EWMH UTF-8, potem klasyczny WM_NAME
            title = ""
            r = win.get_full_property(wm_name_atom, utf8_atom)
            if r is not None and r.value:
                title = r.value.decode("utf-8", "replace")
            else:
                r = win.get_wm_name()
                if isinstance(r, bytes):
                    title = r.decode("latin-1", "replace")
                elif isinstance(r, str):
                    title = r
            state = prop(win, "_NET_WM_STATE")
            if state is not None and net_wm_state_hidden in state:
                continue

            geom = win.get_geometry()
            # prawdziwa sygnatura Xlib: translate_coords(dst, src_x, src_y) —
            # punkt (0,0) okna przelozony na wspolrzedne roota
            tx_ty = win.translate_coords(root, 0, 0)
            # ramka dekoracji okna (tytuł/pas) jeśli WM ją udostępnia
            ext = prop(win, "_NET_FRAME_EXTENTS")
            left = right = top = bottom = 0
            if ext is not None and len(ext) >= 4:
                left, right, top, bottom = (int(v) for v in ext[:4])
            x = tx_ty.x - left
            y = tx_ty.y - top
            w = geom.width + left + right
            h = geom.height + top + bottom
            if w <= 1 or h <= 1:
                continue
            results.append(WindowInfo(
                window_id=int(wid),
                title=title,
                region=(x, y, w, h),
                is_visible=True,
            ))
        return results

    def find_region(self, title_substr: str) -> Optional[Region]:
        needle = title_substr.lower()
        for win in self.list_windows():
            if needle in win.title.lower():
                return win.region
        return None

    def activate(self, title_substr: str) -> bool:
        """Aktywacja okna przez EWMH + (awaryjnie) XSetInputFocus.

        Sam komunikat _NET_ACTIVE_WINDOW zalezy od dobrej woli menedzera okien;
        dla pelnoekranowej gry dodajemy bezposrednie przejecie focusu
        wejsciowego (set_input_focus) i mapowanie okna ukrytego.
        """
        from Xlib import X
        from Xlib.protocol import event
        d = self.display
        root = d.screen().root
        needle = title_substr.lower()
        for win in self.list_windows():
            if needle in win.title.lower():
                xwin = d.create_resource_object("window", win.window_id)
                try:
                    xwin.map_window()   # no-op gdy juz widoczne
                    client_list_atom = d.intern_atom("_NET_ACTIVE_WINDOW")
                    data = [2, 0, X.CurrentTime]  # source: user
                    # Display NIE ma atrybutu .event — komunikaty tworzy
                    # Xlib.protocol.event
                    ev = event.ClientMessage(
                        window=xwin, client_type=client_list_atom, data=(32, data)
                    )
                    root.send_event(
                        ev,
                        event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                    d.flush()
                    # Bezposrednie przejecie focusu — nie zalezy od WM-a
                    xwin.set_input_focus(X.RevertToParent, X.CurrentTime)
                    d.flush()
                except Exception:
                    return False
                delay = get_settings().focus_delay_s
                time.sleep(max(delay, 0.05))
                return True
        return False
