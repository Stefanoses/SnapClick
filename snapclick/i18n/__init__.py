"""Runtime i18n: current language, `t()` translation, persisted preference.

The app core (model, engine, backends) does not know Qt — the
language-changed signal is broadcast through plain listener lists (the GUI
subscribes and switches the UI live). The preference is stored in the
portable settings file next to the app (see ``core.paths``).

With no saved preference the language is detected from the system locale
('pl' -> Polish, otherwise English); with no data at all, default is pl.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..core.paths import settings_file
from .catalogs import CATALOGS

DEFAULT_LANG = "pl"
LANGUAGES: List[str] = ["pl", "en"]

_listener_fns: List[Callable[[str], None]] = []
_current: Optional[str] = None


# ----------------------------------------------------------------- jezyk
def _detect_system_lang() -> str:
    """pl, jezeli locale systemu wskazuje na polski; inaczej en."""
    tags = []
    try:
        import locale
        loc = locale.getlocale()[0]
        if loc:
            tags.append(loc)
    except Exception:
        pass
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            tags.append(val)
    for tag in tags:
        low = tag.lower().replace("-", "_")
        if low.startswith("pl"):
            return "pl"
        if low.startswith("en"):
            return "en"
    return DEFAULT_LANG


def settings_path() -> Path:
    """Portable settings file: ``<app dir>/snapclick-data/settings.json``."""
    return settings_file()


def load_settings() -> None:
    """Wczytuje zapisany jezyk (jesli istnieje); inaczej detekcja locale."""
    global _current
    code = None
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
        cand = str(raw.get("language", "")).lower()
        if cand in CATALOGS:
            code = cand
    except (OSError, ValueError):
        pass  # brak pliku / uszkodzony — detekcja ponizej
    _current = code or _detect_system_lang()


def get_lang() -> str:
    global _current
    if _current is None:
        load_settings()
    assert _current is not None
    return _current


def set_lang(code: str, persist: bool = True) -> bool:
    """Ustawia jezyk + (opcjonalnie) zapisuje preferencje. True gdy zmiana.

    ``persist=False`` dla testow — nie wolno im pisac do ustawien uzytkownika.
    """
    global _current
    if code not in CATALOGS:
        raise ValueError(f"Nieznany jezyk: {code!r}")
    changed = _current != code
    _current = code
    if not persist:
        if changed:
            for fn in list(_listener_fns):
                fn(code)
        return changed
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, object] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except ValueError:
                data = {}
        data["language"] = code
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except OSError:
        pass  # brak prawa zapisu — jezyk dziala do konca sesji
    if changed:
        for fn in list(_listener_fns):
            fn(code)
    return changed


def on_language_changed(fn: Callable[[str], None]) -> None:
    if fn not in _listener_fns:
        _listener_fns.append(fn)


def off_language_changed(fn: Callable[[str], None]) -> None:
    if fn in _listener_fns:
        _listener_fns.remove(fn)


# ------------------------------------------------------------ tlumaczenie
def t(key: str, **kwargs) -> str:
    """Tlumaczenie klucza w biezacym jezyku (z fallbackiem na PL i klucz).

    Wartosci zawieraja pola formatu `{name}` — sa podstawiane przez
    str.format. Blad formatowania (zle kwargs) NIE moze wywrocic UI —
    zwracamy wowczas surowy szablon.
    """
    lang = get_lang()
    text = CATALOGS.get(lang, {}).get(key)
    if text is None:
        text = CATALOGS[DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def choice_label(value: str) -> str:
    """Etykieta wartosci 'choice' (lewy/right/...); brak klucza -> wartosc."""
    key = f"choice.{value}"
    cat = CATALOGS.get(get_lang(), {})
    if key in cat or key in CATALOGS[DEFAULT_LANG]:
        return t(key)
    return value


def language_name(code: str) -> str:
    """Nazwa jezyka we WLasnym jezyku (Polski / English) — stabilna w UI."""
    return t(f"language.{code}")
