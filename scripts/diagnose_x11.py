#!/usr/bin/env python3
"""Diagnostyka X11 dla SnapClick (uruchamiac na docelowym sprzecie, np. Deck).

Cel: ustalic DLACZEGO wpisywanie tekstu nie dociera do okna, skoro mysz
(XTEST) dziala. Skrypt NIE wymaga GUI SnapClick — tylko python-xlib.

Uzycie (w sesji X11, z DISPLAY ustawionym jak dla aplikacji):

    python scripts/diagnose_x11.py            # tylko raport
    python scripts/diagnose_x11.py --key      # + wyślij testowy klawisz 'a'
    python scripts/diagnose_x11.py --text     # + wpisz 'test ŁĄŻ 123'

Wskazowka: odpal w terminalu, ktory MA byc celem — jesli po --key/--text
znaki pojawią sie w tym terminalu, to XTEST i timingi sa OK, a problemem
jest focus/aktywacja okna gry (patrz sekcja FOCUS raportu).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def hr(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", action="store_true",
                    help="wyślij jeden testowy KeyPress/Release ('a')")
    ap.add_argument("--text", action="store_true",
                    help="wpisz 'test ŁĄŻ 123' sciezka backendu X11")
    ap.add_argument("--probe", action="store_true",
                    help="test dostarczenia zdarzen XTEST do wlasnego okna")
    ap.add_argument("--activate", metavar="TYTUL", default=None,
                    help="aktywuj okno o tytule (podstring) i pokaz fokus")
    args = ap.parse_args()

    print(f"Platforma: {sys.platform}  DISPLAY={os.environ.get('DISPLAY')!r}  "
          f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE')!r}  "
          f"WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')!r}")

    try:
        from Xlib import X, display  # noqa: F401
        from Xlib.ext import xtest
    except ImportError:
        print("BLAD: brak python-xlib — `pip install python-xlib`.")
        return 1

    try:
        d = display.Display()
    except Exception as exc:
        print(f"BLAD: nie mozna polaczyc z serwerem X: {exc}")
        return 1
    print(f"Polaczono z X: {d.get_display_name()}  "
          f"ekran={d.get_default_screen()}")

    hr("NARZEDZIA SCHOWKA")
    for tool in ("xclip", "xsel"):
        path = shutil.which(tool)
        print(f"  {tool:6s} -> {path or 'BRAK (sciezka clipboard niedostepna)'}")

    def window_title(win) -> str:
        try:
            r = win.get_full_property(d.intern_atom("_NET_WM_NAME"),
                                      d.intern_atom("UTF8_STRING"))
            if r is not None and r.value:
                return r.value.decode("utf-8", "replace")
            wm = win.get_wm_name()
            return wm.decode("latin-1", "replace") if isinstance(
                wm, bytes) else (wm or "?")
        except Exception as exc:  # okno moglo zniknac
            return f"<blad odczytu: {exc}>"

    hr("OKNO Z FOCUSEM WEJSCIA (cel klawiatury)")
    try:
        focus = d.get_input_focus()
        raw = focus.focus
        # python-xlib zwraca albo obiekt Window, albo surowy int;
        # Xlib.X NIE definiuje stalech PointerRoot/None — to wartosci z
        # protokolu X (X.h): PointerRoot=1, InputFocusNone=0
        fid = int(getattr(raw, "id", raw))
        title = {1: "PointerRoot (serwer, nie okno!)",
                 0: "None (klawisze trafia w proznie!)"}.get(fid)
        if title is None and fid:
            title = window_title(d.create_resource_object("window", fid))
        print(f"  id=0x{fid:x}  tytul={title!r}")
        print("  UWAGA: XTEST wysyla klawisze WLASNIE do tego okna —")
        print("  jesli to nie okno gry, tam trafia tekst (cisza awaria).")
    except Exception as exc:
        print(f"  get_input_focus() -> blad: {exc!r}")

    if args.activate:
        hr(f"AKTYWACJA OKNA '{args.activate}'")
        try:
            from snapclick.core.platform.x11 import X11WindowBackend
            ok = X11WindowBackend().activate(args.activate)
            print(f"  activate() -> {ok}")
            time.sleep(0.3)
            raw = d.get_input_focus().focus
            fid = int(getattr(raw, "id", raw))
            t = (window_title(d.create_resource_object("window", fid))
                 if fid not in (0, 1) else f"<specjalny 0x{fid:x}>")
            print(f"  fokus po aktywacji: 0x{fid:x} {t!r}")
        except Exception as exc:
            print(f"  blad: {exc!r}")

    hr("LISTA OKIEN (backend SnapClick)")
    try:
        from snapclick.core.platform.x11 import X11WindowBackend
        wb = X11WindowBackend()
        wins = wb.list_windows()
        if not wins:
            print("  (pusto — menedzer okien bez EWMH?)")
        for w in wins:
            print(f"  0x{w.window_id:x}  {w.region}  {w.title[:60]!r}")
    except Exception as exc:
        print(f"  list_windows() -> blad: {exc!r}")

    if args.probe:
        hr("PROBE: czy XTEST dostarcza KeyPress do okna z focusem?")
        try:
            from Xlib import X as _X
            from Xlib.ext import xtest as _xt
            root = d.screen().root
            # override_redirect: okno omija menedzera okien — bez tego KWin
            # potrafi odeslac blad protokolu, na ktorym python-xlib sie wywala
            # (BadRRModeError bez sequence_number)
            win = root.create_window(10, 10, 200, 120, 0,
                                     d.screen().root_depth,
                                     _X.InputOutput, _X.CopyFromParent,
                                     override_redirect=1,
                                     event_mask=(_X.KeyPressMask
                                                 | _X.KeyReleaseMask))
            win.map()
            d.flush()
            win.set_input_focus(_X.RevertToParent, _X.CurrentTime)
            d.flush()
            time.sleep(0.4)
            keycode = d.keysym_to_keycode(0x61)          # 'a'
            # XTEST bierze KOD ZDARZENIA X11: KeyPress=2, KeyRelease=3
            # (4/5 to przyciski myszy — blad serwera + crash python-xlib)
            _xt.fake_input(d, _X.KeyPress, keycode)
            d.flush()
            time.sleep(0.05)
            _xt.fake_input(d, _X.KeyRelease, keycode)
            d.flush()
            got_press = got_release = False
            deadline = time.time() + 2.0
            while time.time() < deadline and not (got_press and got_release):
                if d.pending_events():
                    ev = d.next_event()
                    if ev.type == _X.KeyPress:
                        got_press = True
                    elif ev.type == _X.KeyRelease:
                        got_release = True
                else:
                    time.sleep(0.02)
            win.destroy()
            d.flush()
            print(f"  KeyPress dotarl:   {got_press}")
            print(f"  KeyRelease dotarl: {got_release}")
            if got_press and got_release:
                print("  WNIOSKEK: XTEST + fokus dzialaja — problem lezy")
                print("  w oknie docelowym (focus/aktywacja gry).")
            else:
                print("  WNIOSKEK: XTEST NIE dostarcza klawiszy do okna")
                print("  z focusem — rozszerzenie XTEST/serwer X blokuje")
                print("  wstrzykiwanie klawiatury.")
        except Exception as exc:
            print(f"  blad proby: {exc!r}")

    hr("TEST XTEST (klawiatura)")
    if args.key or args.text:
        from snapclick.core.platform.x11 import X11InputBackend
        b = X11InputBackend()
        print("  Za 3 s wysle znaki do okna z FOCUSEM — przejdź teraz do")
        print("  terminala/polа, ktore ma je przyjac, i patrz czy wpadna.")
        time.sleep(3)
        if args.key:
            b.press_combo("a")
            print("  wyslano: press_combo('a')")
        if args.text:
            b.type_text("test ŁĄŻ 123", method="type")
            print("  wyslano: type_text('test ŁĄŻ 123', method='type')")
    else:
        print("  (pominieto — uzyj --key lub --text)")

    hr("PODSUMOWANIE")
    print("  1. Znaki wpadaja tam, gdzie OKNO Z FOCUSEM — nie tam, gdzie kursor.")
    print("  2. Jesli w SnapClick ustawiony tytul okna gry, fokus ustawia")
    print("     activate(); porownaj 'OKNO Z FOCUSEM' z 'LISTA OKIEN'.")
    print("  3. Jesli fokus = PointerRoot/None — WM nie przekazuje focusu;")
    print("     w grze/emulatorze kliknij najpierw w jej okno blokiem CLICK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
