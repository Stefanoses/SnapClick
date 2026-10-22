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

    hr("OKNO Z FOCUSEM WEJSCIA (cel klawiatury)")
    try:
        focus = d.get_input_focus()
        fid = int(focus.focus)
        names = {int(d.intern_atom(n)): n for n in
                 ("_NET_WM_NAME", "WM_NAME")}
        title = None
        if fid in (X.InputFocusPointerRoot, X.InputFocusNone,
                   getattr(X, "InputFocusFollowsPointer", 0)):
            title = {X.InputFocusPointerRoot: "PointerRoot (serwer, nie okno!)",
                     X.InputFocusNone: "None (klawisze trafia w proznie!)"}.get(fid)
        if title is None and fid:
            win = d.create_resource_object("window", fid)
            try:
                r = win.get_full_property(d.intern_atom("_NET_WM_NAME"),
                                          d.intern_atom("UTF8_STRING"))
                if r is not None and r.value:
                    title = r.value.decode("utf-8", "replace")
                else:
                    wm = win.get_wm_name()
                    title = wm.decode("latin-1", "replace") if isinstance(
                        wm, bytes) else (wm or "?")
            except Exception as exc:  # okno moglo zniknac
                title = f"<blad odczytu: {exc}>"
        print(f"  id=0x{fid:x}  tytul={title!r}")
        print("  UWAGA: XTEST wysyla klawisze WLASNIE do tego okna —")
        print("  jesli to nie okno gry, tam trafia tekst (cisza awaria).")
    except Exception as exc:
        print(f"  get_input_focus() -> blad: {exc}")

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
