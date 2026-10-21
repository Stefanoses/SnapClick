"""Wspólne fixture'y: moki backendów i tymczasowe katalogi projektów."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Upewnij się, że korzeń repo jest na sys.path (import snapclick bez instalacji).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Deterministyczny język testów: komunikaty walidacji/silnika są tłumaczone
# (i18n), a testy matchują wzorce po polsku. Wymuszamy 'pl' bez zapisywania
# preferencji (persist=False) — ustawienia użytkownika muszą zostać nietknięte.
from snapclick.i18n import set_lang  # noqa: E402

set_lang("pl", persist=False)


class FakeScreen:
    """ScreenBackend zdefiniowany przez użytkownika: funkcja renderująca klatkę.

    ``monitors`` (opcjonalnie) — lista MonitorInfo odwzorowywana przez
    testowana logike wielomonitorowa; bez niej backend 'nie zna' monitorow.
    """

    def __init__(self, frame_fn, monitors=None) -> None:
        self._frame_fn = frame_fn
        self.grab_calls = 0
        self._monitors = monitors

    def grab(self, region=None):
        self.grab_calls += 1
        return self._frame_fn(region)

    def monitors(self):
        return list(self._monitors) if self._monitors else []

    def virtual_bounds(self):
        if not self._monitors:
            return (0, 0, 1920, 1080)
        x0 = min(m.region[0] for m in self._monitors)
        y0 = min(m.region[1] for m in self._monitors)
        x1 = max(m.region[0] + m.region[2] for m in self._monitors)
        y1 = max(m.region[1] + m.region[3] for m in self._monitors)
        return (x0, y0, x1 - x0, y1 - y0)

    def primary_size(self):
        return (1920, 1080)


class FakeInput:
    """Zapisuje wszystkie akcje wejścia do listy ``actions``."""

    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def move(self, x, y):
        self.actions.append(("move", x, y))

    def click(self, x, y, button="left", double=False):
        self.actions.append(("click", x, y, button, double))

    def press_combo(self, combo):
        self.actions.append(("combo", combo))

    def type_text(self, text, method="auto"):
        self.actions.append(("type", text, method))

    def set_clipboard(self, text):
        self.actions.append(("clipboard", text))


class FakeWindows:
    """Okno 'MyApp' o z góry ustalonym regionie."""

    def __init__(self, region=(100, 50, 800, 600)) -> None:
        self.region = region

    def list_windows(self):
        return []

    def find_region(self, title_substr):
        return self.region if "myapp" in (title_substr or "").lower() else None

    def activate(self, title_substr):
        return True


class FakeTemplateRegistry:
    """TemplateRegistry trzymający tablice w słowniku (bez dysku)."""

    def __init__(self, images: dict[str, np.ndarray]) -> None:
        self._images = images

    def get(self, t_id):
        from snapclick.core.platform.base import BackendError
        if t_id not in self._images:
            raise BackendError(f"Brak szablonu: {t_id}")
        return self._images[t_id]

    def meta(self, t_id):
        return None


@pytest.fixture
def fake_screen_factory():
    return FakeScreen


@pytest.fixture
def fake_input():
    return FakeInput()


@pytest.fixture
def fake_windows():
    return FakeWindows()
