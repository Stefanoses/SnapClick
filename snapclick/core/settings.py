"""Globalne ustawienia aplikacji (timing wejścia, focus okna).

Zapis w tym samym pliku co preferencja jezyka (``i18n.settings_path()``),
klucz ``"input"`` — zapis scalany istniejacym JSON-em, wiec jezyk i timingi
nie nadpisuja sie nawzajem.

Sens parametrow (dlaczego niektore gry ignoruja klik):
  * ``click_method``      — ``sendinput``: klik przez kolejke wejsc systemu
                            (czyta go DirectInput/OpenGL; antybot z flaga
                            "injected" moze wyrzucac przyciski).
                            ``postmessage``: WM_*BUTTONDOWN/UP wysylane
                            bezposrednio do HWND okna gry (PostMessage) —
                            omija kolejke wejsc i jej filtry; wymaga
                            zidentyfikowanego okna w programie (tytul okna).
  * ``mouse_hold_s``      — czas miedzy ButtonPress a ButtonRelease. Wyslane
                            "natychmiast" (0 ms) zdarzenia SendInput bywaja
                            gubione przez kolejke DirectInput gry.
  * ``move_settle_s``     — pauza miedzy przeniesieniem kursora a wcisnieciem
                            (gry/przetwarzanie hover potrzebuja ~1 klatki).
  * ``double_gap_s``      — odstep miedzy parami klikniec przy dwukliku.
  * ``release_settle_s``  — odstep po puszczeniu przycisku (next action).
  * ``focus_enabled``     — czy silnik ma przywodzic okno gry na wierzch
                            przed przebiegiem (AttachThreadInput / EWMH).
  * ``focus_after_click`` — aktywacja przed KAZDYM kliknieciem (ostatecznosc;
                            wolniejsze, pomaga gdy okno traci focus w trakcie).
  * ``focus_delay_s``     — czas dawany oknu na przejecie focusu po aktywacji.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional

from ..i18n import settings_path

_INPUT_SECTION = "input"


@dataclass
class InputSettings:
    """Timing i zachowanie warstwy wejsciowej (mysz + focus okna)."""

    click_method: str = "sendinput"
    type_method: str = "auto"
    mouse_hold_s: float = 0.06
    move_settle_s: float = 0.05
    double_gap_s: float = 0.05
    release_settle_s: float = 0.02
    focus_enabled: bool = True
    focus_after_click: bool = False
    focus_delay_s: float = 0.15

    def validate(self) -> "InputSettings":
        """Przycinanie do zdrowych zakresow (plik JSON moze byc reczny)."""
        if self.click_method not in ("sendinput", "postmessage"):
            self.click_method = "sendinput"
        if self.type_method not in ("auto", "sendinput", "postmessage"):
            self.type_method = "auto"
        limits = {
            "mouse_hold_s": (0.0, 2.0),
            "move_settle_s": (0.0, 2.0),
            "double_gap_s": (0.01, 1.0),
            "release_settle_s": (0.0, 2.0),
            "focus_delay_s": (0.0, 5.0),
        }
        for f in fields(self):
            if f.name in limits:
                lo, hi = limits[f.name]
                setattr(self, f.name, min(max(float(getattr(self, f.name)), lo), hi))
        return self


def _read_raw() -> Dict[str, Any]:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_input_settings() -> InputSettings:
    """Wczytuje timing z pliku; brak/awaria -> wartosci domyslne."""
    section = _read_raw().get(_INPUT_SECTION)
    if not isinstance(section, dict):
        return InputSettings()
    kwargs: Dict[str, Any] = {}
    for f in fields(InputSettings):
        if f.name not in section:
            continue
        value = section[f.name]
        if f.type == "str":
            kwargs[f.name] = str(value)
            continue
        try:
            kwargs[f.name] = bool(value) if f.type == "bool" else float(value)
        except (TypeError, ValueError):
            continue  # smieciowa wartosc -> domyslna
    return InputSettings(**kwargs).validate()


def save_input_settings(settings: InputSettings) -> None:
    """Zapisuje timing, zachowujac pozostale klucze (np. 'language')."""
    path = settings_path()
    data = _read_raw()
    data[_INPUT_SECTION] = asdict(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


# ------------------------------------------------------------ singleton
_current: Optional[InputSettings] = None


def get_settings() -> InputSettings:
    """Leniwie ladowany shared instance (backendy/interpreter czytaja z niego)."""
    global _current
    if _current is None:
        _current = load_input_settings()
    return _current


def set_settings(settings: InputSettings, persist: bool = True) -> None:
    """Podmienia singleton (testu moga wstrzykniec wlasny; persist=False)."""
    global _current
    _current = settings.validate()
    if persist:
        save_input_settings(_current)


def reload_settings() -> InputSettings:
    global _current
    _current = load_input_settings()
    return _current
