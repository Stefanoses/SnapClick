"""Backend platformy Windows 11.

- Ruch myszy: natywny ``SendInput`` (ABSOLUTE|VIRTUALDESK).
- Kliknięcia (do wyboru w ustawieniach):
    * ``sendinput``   — przyciski przez kolejkę wejść z REALNYM przytrzymaniem
      (pydirectinput.click() wysyła press+release w jednym pakiecie — hold 0 ms
      i DirectInput gry gubią taki impuls).
    * ``postmessage`` — WM_*BUTTONDOWN/UP przez PostMessage wprost do HWND pod
      punktem kliknięcia. Oprogramowanie antybotowe potrafi odrzucać
      przyciski z flagą "injected" w kolejce SendInput — kolejka komunikatów
      okna (jak AutoIt ControlClick) nie jest filtrowana w ten sposób.
- Klawiatura: pydirectinput (scankody) + SendInput KEYEVENTF_UNICODE (Unicode).
- Okna: ctypes + user32 (EnumWindows / GetWindowRect) oraz ``bring_to_front``
  (AttachThreadInput + foreground-lock timeout) — BEZ keybd_event(ALT), który
  jest sygnaturą "ResetInputState" wykrywaną przez antyboty, i bez
  ShowWindow(SW_RESTORE), które zdejmuje maksymalizację z okna borderless.
- Współrzędne: pikselne fizyczne — wymaga włączonego DPI awareness
  (``enable_dpi_awareness`` wywoływane w ``snapclick/__main__.py``).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from typing import List, Optional, Tuple

from .base import BackendError, Region, WindowInfo
from ..settings import get_settings

# --------------------------------------------------------------------- DPI


def enable_dpi_awareness() -> None:
    """Ustawia proces jako per-monitor DPI aware (Windows 8.1+).

    Bez tego przy skalowaniu 125/150% zrzuty mss i kliknięcia pydirectinput
    rozmijają się z rzeczywistością.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # fallback system-aware
        except Exception:  # pragma: no cover - starsze Windows bez API
            pass


def _import_pydirectinput():
    try:
        import pydirectinput
    except ImportError as exc:  # pragma: no cover
        raise BackendError(
            "Brak pakietu pydirectinput (pip install pydirectinput)."
        ) from exc
    # Bot sam steruje pacingiem — wyłącz domyślne PAUSE pyautogui 0.1 s.
    pydirectinput.PAUSE = 0.0
    pydirectinput.FAILSAFE = False
    return pydirectinput


# --------------------------------------------------------------------- input

_COMBO_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift",
    "win": "win", "super": "win", "enter": "enter", "esc": "esc",
    "space": "space", "tab": "tab", "backspace": "backspace",
    "delete": "delete", "del": "delete",
}


class Win32InputBackend:
    """Wstrzykiwanie wejść: SendInput lub PostMessage (zależnie od ustawień)."""

    name = "win32-sendinput"

    def __init__(self) -> None:
        self._pdid = _import_pydirectinput()
        self._target_hwnd: Optional[int] = None

    def set_target_window(self, window_id: Optional[int]) -> None:
        """HWND okna gry — awaryjny cel klików PostMessage (interpreter)."""
        self._target_hwnd = int(window_id) if window_id else None

    # -------------------------------------------------------------- mouse
    def move(self, x: int, y: int) -> None:
        win_move_abs(int(x), int(y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        """Klik 'jak człowiek': ruch -> settle -> press -> HOLD -> release.

        Sposób dostarczenia przycisków wybiera ``settings.click_method`` —
        patrz docstring modułu.
        """
        btn = {"left": "left", "right": "right", "middle": "middle"}.get(button, "left")
        st = get_settings()
        win_move_abs(int(x), int(y))
        if st.move_settle_s > 0:
            time.sleep(st.move_settle_s)
        if st.click_method == "postmessage":
            self._click_postmessage(int(x), int(y), btn, double, st)
        else:
            self._click_sendinput(btn, double, st)
        if st.release_settle_s > 0:
            time.sleep(st.release_settle_s)

    def _click_sendinput(self, btn: str, double: bool, st) -> None:
        presses = 2 if double else 1
        for i in range(presses):
            win_button(btn, down=True)
            if st.mouse_hold_s > 0:
                time.sleep(st.mouse_hold_s)
            win_button(btn, down=False)
            if i < presses - 1 and st.double_gap_s > 0:
                time.sleep(st.double_gap_s)

    def _click_postmessage(self, x: int, y: int, btn: str, double: bool,
                           st) -> None:
        """Press/release jako komunikaty okna — poza kolejką wejść systemu."""
        hwnd = win_window_at_point(x, y) or (self._target_hwnd or 0)
        if not hwnd:
            raise BackendError(
                "Klik PostMessage wymaga okna gry — uzupełnij 'Tytuł okna' w "
                "ustawieniach programu albo przełącz metodę na SendInput.")
        cx, cy = win_screen_to_client(hwnd, x, y)
        down_msg, up_msg, mk = _BUTTON_MSGS[btn]
        win_post_message(hwnd, _WM_MOUSEMOVE, 0, cx, cy)
        presses = 2 if double else 1
        for i in range(presses):
            win_post_message(hwnd, down_msg, mk, cx, cy)
            if st.mouse_hold_s > 0:
                time.sleep(st.mouse_hold_s)
            win_post_message(hwnd, up_msg, 0, cx, cy)
            if i < presses - 1 and st.double_gap_s > 0:
                time.sleep(st.double_gap_s)

    # ---------------------------------------------------------- keyboard
    def press_combo(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.replace("+", ",").split(",") if p.strip()]
        if not parts:
            raise BackendError(f"Pusto zdefiniowane combo klawiszy: {combo!r}")
        keys = [_COMBO_ALIASES.get(p, p) for p in parts]
        if len(keys) == 1:
            self._pdid.press(keys[0])
        else:
            self._pdid.hotkey(*keys)

    def type_text(self, text: str, method: str = "auto") -> None:
        # Rozwiazanie "auto": globalny typ_method (Ustawienia wejścia), az do
        # poziomu bloku — metody kliku i klawiatury sa NIEZALEZNE (klient moze
        # np. klikac przez SendInput, a tekst potrzebowac WM_CHAR).
        if method == "auto":
            method = get_settings().type_method
        if method == "auto":
            method = "clipboard"  # stare, wyjsciowe zachowanie
        if method == "sendinput":
            method = "type"
        if method == "postmessage":
            self._type_postmessage(text)
            return
        if method in ("auto", "clipboard") and self._clipboard_available():
            self.set_clipboard(text)
            self._pdid.hotkey("ctrl", "v")
            return
        if method == "clipboard":
            raise BackendError("Schowek niedostępny — użyj method='type'.")
        # Metoda "type": SendInput + KEYEVENTF_UNICODE — pelny Unicode (ł, ą, ż).
        # Stara sciezka przez pydirectinput.write() miala mapowanie ASCII i po
        # cichu pomijala znaki poza mapa — stad "znikajace" polskie znaki.
        for ch in text:
            if ch == "\n":
                self._pdid.press("enter")
            else:
                win_type_char(ch)

    def _type_postmessage(self, text: str) -> None:
        """Wpisywanie znak po znaku przez trio WM_KEYDOWN/WM_CHAR/WM_KEYUP.

        Sam WM_CHAR wystarcza polom, ktore powoduja TranslateMessage, ale
        wlasne pola tekstowe klientow gier czesto nasluchuja
        wylacznie WM_KEYDOWN (obsługa kursora/backspace) — stad peleton jak w
        AutoIt ControlSend: KEYDOWN -> CHAR -> KEYUP. Okno klienta jest ANSI
        (cp1250), wiec znaki spoza ASCII konwertujemy na bajt cp1250; surowy
        Unicode (0x142 dla 'ł') zostalby przez okno ANSI obciety do 0x42 ('B').
        """
        # Cel: okno gry z programu (pewne) > biezacy foreground (awaryjnie).
        # Gdybysmy brali foreground jako pierwszy, przy wylaczonym focusie
        # znaki wlecialyby np. do okna naszej aplikacji.
        hwnd = self._target_hwnd or _GET_FOREGROUND_WINDOW() or 0
        if not hwnd:
            raise BackendError(
                "Wpisywanie PostMessage wymaga aktywnego okna gry lub "
                "uzupelnionego 'Tytul okna' w programie.")
        for ch in text:
            win_post_char(hwnd, ch)
            time.sleep(0.012)  # pacing — kolejka okna nie lubi zalewania

    # ---------------------------------------------------------- clipboard
    def _clipboard_available(self) -> bool:
        return True

    def set_clipboard(self, text: str) -> None:
        _win_set_clipboard(text)


# CF_UNICODETEXT = 13
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _win_set_clipboard(text: str) -> None:
    if not _user32.OpenClipboard(None):
        raise BackendError("Nie można otworzyć schowka Windows.")
    try:
        _user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not h_mem:
            raise BackendError("GlobalAlloc nie przydzielił pamięci schowka.")
        ptr = _kernel32.GlobalLock(h_mem)
        if not ptr:
            _kernel32.GlobalFree(h_mem)
            raise BackendError("GlobalLock nie zablokował pamięci schowka.")
        ctypes.memmove(ptr, data, len(data))
        _kernel32.GlobalUnlock(h_mem)
        if not _user32.SetClipboardData(_CF_UNICODETEXT, h_mem):
            _kernel32.GlobalFree(h_mem)
            raise BackendError("SetClipboardData odrzuciło dane.")
        # Po SetClipboardData własność pamięci przejmuje system — nie zwalniamy.
    finally:
        _user32.CloseClipboard()


# ------------------------------------------------- Unicode przez SendInput
#
# KEYEVENTF_UNICODE wstrzykuje zdarzenia klawiatury z bezposrednim kodem
# UTF-16 (pole wScan), wiec dziala dla kazdego znaku Unicode niezaleznie od
# ukladu klawiatury — w przeciwienstwie do scankodow pydirectinput (ASCII).
# To standardowa technika aplikacji typu AutoHotkey/xdotool; aplikacje
# DirectX/OpenGL czytajace WM_CHAR tez ja odbieraja.

_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_KEYUP = 0x0002
_INPUT_KEYBOARD = 1


class _MOUSEINPUT(ctypes.Structure):
    # wymagany do prawidlowego rozmiaru unii INPUT
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _unicode_units(ch: str) -> List[int]:
    """Jednostki kodu UTF-16 znaku (para surrogate dla znakow ponad BMP)."""
    data = ch.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little")
            for i in range(0, len(data), 2)]


def _kbd_event(unit: int, flags: int) -> "_INPUT":
    event = _INPUT()
    event.type = _INPUT_KEYBOARD
    event.ki = _KEYBDINPUT(wVk=0, wScan=unit, dwFlags=flags, time=0,
                           dwExtraInfo=None)
    return event


def _win_send_inputs(events: List["_INPUT"]) -> None:
    arr = (_INPUT * len(events))(*events)
    sent = _user32.SendInput(len(events), ctypes.byref(arr),
                             ctypes.sizeof(_INPUT))
    if sent != len(events):  # pragma: no cover - blokada UIPI itp.
        raise BackendError(
            f"SendInput przyjal {sent}/{len(events)} zdarzen wejścia "
            "(okno moze byc uruchomione jako administrator).")


# ----------------------------------------------------- mysz przez SendInput
#
# Wlasna implementacja zamiast pydirectinput.click(): ten wysyla pare
# press+release w JEDNYM pakiecie (hold ~0 ms). DirectInput gier odpytuje
# stan przycisku w kolejnych klatkach — zerowy impuls bywa niewidoczny.
# Tu kazde zdarzenie idzie osobnym SendInput, a miedzy nimi jest realne
# przytrzymanie (settings.mouse_hold_s).

_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_MOUSEEVENTF_ABSOLUTE = 0x8000

_BUTTON_FLAGS = {
    "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
    "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
    "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
}

# SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN/SM_CXVIRTUALSCREEN/SM_CYVIRTUALSCREEN
_SM_XV, _SM_YV, _SM_CXV, _SM_CYV = 76, 77, 78, 79


def _mouse_event(flags: int, dx: int = 0, dy: int = 0) -> "_INPUT":
    event = _INPUT()
    event.type = _INPUT_MOUSE
    event.mi = _MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=flags, time=0,
                           dwExtraInfo=None)
    return event


def win_move_abs(x: int, y: int) -> None:
    """Ruch kursora do punktu WIRTUALNEGO pulpitu (0,0 = lewy gorany monitor).

    SendInput z MOUSEEVENTF_ABSOLUTE normalizuje wspolrzedne do 0..65535 na
    calym wirtualnym pulpicie — mnoznik liczony z GetSystemMetrics (dokladnie
    tak robi pydirectinput, tylko bez pauzy miedzy zdarzeniami).
    """
    vx = _user32.GetSystemMetrics(_SM_XV)
    vy = _user32.GetSystemMetrics(_SM_YV)
    vw = max(_user32.GetSystemMetrics(_SM_CXV), 1)
    vh = max(_user32.GetSystemMetrics(_SM_CYV), 1)
    nx = int((x - vx) * 65535 / max(vw - 1, 1))
    ny = int((y - vy) * 65535 / max(vh - 1, 1))
    nx = min(max(nx, 0), 65535)
    ny = min(max(ny, 0), 65535)
    _win_send_inputs([_mouse_event(_MOUSEEVENTF_MOVE
                                   | _MOUSEEVENTF_ABSOLUTE
                                   | _MOUSEEVENTF_VIRTUALDESK, nx, ny)])


def win_button(button: str, down: bool) -> None:
    """Wcisniecia/puszczenie przycisku myszy jako POJEDYNCZE zdarzenie."""
    pair = _BUTTON_FLAGS.get(button)
    if pair is None:
        raise BackendError(f"Nieznany przycisk myszy: {button!r}")
    _win_send_inputs([_mouse_event(pair[0] if down else pair[1])])


# ----------------------------------------------- klik przez PostMessage
#
# Oprogramowanie antybotowe odrzuca przyciski myszy z
# flaga "injected" w kolejce SendInput (ruch zwykle przechodzi, klik nie).
# Wiadomosci WM_*BUTTONDOWN/UP wyslane PostMessage trafiaja bezposrednio do
# kolejki komunikatow okna i nie sa oznaczane jako wstrzykniete wejscia — tak
# dzialal ControlClick w botach AutoIt. Dwa niuanse decyduja o skutecznosci:
#   1. wspolrzedne musza byc w ukladzie KLIENT okna-docelowego (ScreenToClient);
#   2. oknem pobierajacym input bywa DZIECKO renderujace gre, nie okno
#      glowne — dlatego cel rozwiazuje WindowFromPoint(punkt), a HWND z
#      enumeracji tytulu jest tylko awaryjnym fallbackiem.

_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_WM_MBUTTONDOWN = 0x0207
_WM_MBUTTONUP = 0x0208
_MK_LBUTTON = 0x0001
_MK_RBUTTON = 0x0002
_MK_MBUTTON = 0x0010

_BUTTON_MSGS = {
    "left": (_WM_LBUTTONDOWN, _WM_LBUTTONUP, _MK_LBUTTON),
    "right": (_WM_RBUTTONDOWN, _WM_RBUTTONUP, _MK_RBUTTON),
    "middle": (_WM_MBUTTONDOWN, _WM_MBUTTONUP, _MK_MBUTTON),
}


def _lparam(x: int, y: int) -> int:
    """MAKELPARAM: x w niskim slowie, y w wysokim (16 bitow, ze znakiem)."""
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def win_window_at_point(x: int, y: int) -> int:
    """HWND okna (rowniez dzieciecego) bezposrednio pod punktem ekranu."""
    pt = wintypes.POINT(int(x), int(y))
    hwnd = _user32.WindowFromPoint(pt)
    return int(hwnd) if hwnd else 0


def win_screen_to_client(hwnd: int, x: int, y: int) -> Tuple[int, int]:
    pt = wintypes.POINT(int(x), int(y))
    if not _user32.ScreenToClient(wintypes.HWND(int(hwnd)), ctypes.byref(pt)):
        raise BackendError("ScreenToClient nie zwrocilo wspolrzednych klienta.")
    return int(pt.x), int(pt.y)


def win_post_message(hwnd: int, msg: int, wparam: int, x: int, y: int) -> None:
    ok = _user32.PostMessageW(wintypes.HWND(int(hwnd)), wintypes.UINT(msg),
                              wintypes.WPARAM(int(wparam)),
                              wintypes.LPARAM(_lparam(x, y)))
    if not ok:  # pragma: no cover - okno moglo zostac zamkniete w trakcie
        raise BackendError(f"PostMessage (msg={msg:#06x}) zostalo odrzucone.")


_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_CHAR = 0x0102
_VK_RETURN = 0x0D
# lParam WM_KEYUP: repeat=1, previous key state=1, transition=1 (30. bit)
_LP_KEYUP = ctypes.c_int32(0xC0000001).value


def win_char_wparam(ch: str) -> int:
    """wParam dla WM_CHAR: ASCII 1:1, poza ASCII — bajt cp1250 (okno ANSI),
    a gdy znak nie istnieje w cp1250 — pelny punkt kodowy Unicode."""
    if ord(ch) < 0x80:
        return ord(ch)
    try:
        return ch.encode("cp1250")[0]
    except (UnicodeEncodeError, LookupError):
        return ord(ch)


_user32.VkKeyScanW.restype = ctypes.c_short   # SHORT; -1 = brak mapowania
_user32.VkKeyScanW.argtypes = [wintypes.WCHAR]


def win_vk_of(ch: str) -> int:
    """Virtual-key code znaku wg ukladu klawiatury (0 = brak mapowania)."""
    if ch == "\n":
        return _VK_RETURN
    scan = _user32.VkKeyScanW(ch)
    return (scan & 0xFF) if scan != -1 else 0


def _post(hwnd: int, msg: int, wparam: int, lparam: int) -> None:
    ok = _user32.PostMessageW(wintypes.HWND(int(hwnd)), wintypes.UINT(msg),
                              wintypes.WPARAM(int(wparam)),
                              wintypes.LPARAM(int(lparam)))
    if not ok:  # pragma: no cover - okno moglo zostac zamkniete w trakcie
        raise BackendError(f"PostMessage (msg={msg:#06x}) zostalo odrzucone.")


def win_post_char(hwnd: int, ch: str) -> None:
    """Pojedynczy znak jako KEYDOWN -> CHAR -> KEYUP (jak ControlSend).

    Pola czytajace wylacznie WM_KEYDOWN dostaja wlasciwy VK, pola czytajace
    WM_CHAR dostaja zakodowany znak, a obsluga focusu/kursora widzi pelny
    cykl klawisza. Znaki bez mapowania VK (np. spoza ukladu) ida jako goly
    WM_CHAR.
    """
    vk = win_vk_of(ch)
    code = _VK_RETURN if ch == "\n" else win_char_wparam(ch)
    if vk:
        _post(hwnd, _WM_KEYDOWN, vk, 1)
    _post(hwnd, _WM_CHAR, code, 1)
    if vk:
        _post(hwnd, _WM_KEYUP, vk, _LP_KEYUP)


def win_type_char(ch: str) -> None:
    """Wstrzykuje pojedynczy znak przez KEYEVENTF_UNICODE (pelny Unicode)."""
    for unit in _unicode_units(ch):
        _win_send_inputs([
            _kbd_event(unit, _KEYEVENTF_UNICODE),
            _kbd_event(unit, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP),
        ])
        time.sleep(0.008)  # odstepy jak przy realnym pisaniu (pacing)


# --------------------------------------------------------------------- windows

_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class Win32WindowBackend:
    """Enumeracja okien desktopu przez user32."""

    name = "win32-user32"

    def list_windows(self) -> List[WindowInfo]:
        results: List[WindowInfo] = []

        def cb(hwnd, _lparam):  # noqa: ANN001
            if not _user32.IsWindowVisible(hwnd):
                return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            rect = wintypes.RECT()
            if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w <= 1 or h <= 1:
                return True
            results.append(WindowInfo(
                window_id=int(hwnd),
                title=buf.value,
                region=(rect.left, rect.top, w, h),
                is_visible=True,
            ))
            return True

        _user32.EnumWindows(_EnumWindowsProc(cb), 0)
        return results

    def find_region(self, title_substr: str) -> Optional[Region]:
        needle = title_substr.lower()
        for win in self.list_windows():
            if needle in win.title.lower():
                return win.region
        return None

    def find_hwnd(self, title_substr: str) -> int:
        """HWND pierwszego okna z podstringiem w tytule (0 = brak)."""
        needle = title_substr.lower()
        for win in self.list_windows():
            if needle in win.title.lower():
                return int(win.window_id)
        return 0

    def activate(self, title_substr: str) -> bool:
        needle = title_substr.lower()
        for win in self.list_windows():
            if needle in win.title.lower():
                ok = bring_to_front(wintypes.HWND(win.window_id))
                delay = get_settings().focus_delay_s
                time.sleep(max(delay, 0.05))  # okno musi przejac focus
                return ok
        return False


# --------------------------------------------------------------- focus okna
#
# Windows blokuje SetForegroundWindow procesom "nieaktywnym" (anti-focus-
# -hijacking): klik w tle naszego bota = okno gry NIE dostaje focusu i gra
# (DirectInput) ignoruje mysz. Standardowe obejscie (AutoHotkey itp.):
# AttachThreadInput z watkiem aktywnego okna + chwilowe "stukniecie" ALT
# (ResetInputState) + AllowSetForegroundWindow.

_ATTACH_THREAD_INPUT = ctypes.windll.user32.AttachThreadInput
_GET_FOREGROUND_WINDOW = ctypes.windll.user32.GetForegroundWindow
_GET_WINDOW_THREAD_ID = ctypes.windll.user32.GetWindowThreadProcessId
_GET_CURRENT_THREAD_ID = ctypes.windll.kernel32.GetCurrentThreadId
_ALLOW_SET_FOREGROUND = ctypes.windll.user32.AllowSetForegroundWindow
_IS_ICONIC = ctypes.windll.user32.IsIconic
_BRING_WINDOW_TO_TOP = ctypes.windll.user32.BringWindowToTop

# (usunięte: VK_MENU/keybd_event — sygnatura ResetInputState wykrywana przez
#  antyboty; focus realizuje foreground-lock timeout poniżej)


_SPI_GETFOREGROUNDLOCK_TIMEOUT = 0x2000
_SPI_SETFOREGROUNDLOCK_TIMEOUT = 0x1000


def _clear_foreground_lock() -> int:
    """Zapamietuje i zeruje ForegroundLockTimeout (ms; 0 = brak blokady).

    Windows odrzuca SetForegroundWindow procesu, ktory nie jest "aktywny".
    Chwilowe wyzerowanie timeoutu (user32 SPI) odblokowuje przejecie focusu
    bez generowania fałszywych klawiszy — keybd_event(VK_MENU) bywa wykrywany
    przez antyboty jako sygnatura ResetInputState i blokuje wtedy CALY input.
    """
    prev = wintypes.UINT(0)
    _user32.SystemParametersInfoW(_SPI_GETFOREGROUNDLOCK_TIMEOUT, 0,
                                  ctypes.byref(prev), 0)
    _user32.SystemParametersInfoW(_SPI_SETFOREGROUNDLOCK_TIMEOUT, 0, None, 0)
    return int(prev.value)


def _restore_foreground_lock(seconds: int) -> None:
    _user32.SystemParametersInfoW(_SPI_SETFOREGROUNDLOCK_TIMEOUT, 0,
                                  ctypes.c_void_p(int(seconds)), 0)


def bring_to_front(hwnd: "wintypes.HWND") -> bool:
    """Przywołuje okno na wierzch mimo ograniczeń anti-hijack Windowsa.

    Bez ShowWindow(SW_RESTORE) na oknie normalnym: dla okna borderless
    (maksymalizowanego) zdejmowaloby to maksymalizacje. Zminimalizowane
    okno najpierw SW_RESTORE, potem SW_MAXIMIZE — stan wyjsciowy zachowany.
    """
    if _IS_ICONIC(hwnd):
        _user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        _user32.ShowWindow(hwnd, 3)   # SW_MAXIMIZE (borderless gra)
    if _user32.SetForegroundWindow(hwnd):
        return True

    # Awaryjnie: dolacz watek do watku aktywnego okna (wspoldziela stan
    # foregroundu) + zresetuj "lock" na czas przejecia.
    fg = _GET_FOREGROUND_WINDOW()
    tid_me = _GET_CURRENT_THREAD_ID()
    tid_fg = _GET_WINDOW_THREAD_ID(fg, None) if fg else 0
    attached = False
    if tid_fg and tid_fg != tid_me:
        attached = bool(_ATTACH_THREAD_INPUT(tid_me, tid_fg, True))
    lock_prev = _clear_foreground_lock()
    try:
        if attached:
            _BRING_WINDOW_TO_TOP(hwnd)
            _user32.SetActiveWindow(hwnd)
        _ALLOW_SET_FOREGROUND(-1)  # ASFW_ANY
        ok = bool(_user32.SetForegroundWindow(hwnd))
        if attached:
            _user32.BringWindowToTop(hwnd)
        return ok
    finally:
        _restore_foreground_lock(lock_prev)
        if attached:
            _ATTACH_THREAD_INPUT(tid_me, tid_fg, False)
