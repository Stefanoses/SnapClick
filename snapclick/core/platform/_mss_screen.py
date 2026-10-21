"""Współdzielony dla Windows i Linux backend zrzutów ekranu oparty na ``mss``.

``mss`` nie jest thread-safe — trzymamy jedną instancję na wątek
(``threading.local``), bo interpreter działa w wątku roboczym,
a narzędzie przechwycenia szablonów w wątku GUI.
"""
from __future__ import annotations

import threading
from typing import Any, Optional, Tuple

import numpy as np

from .base import BackendError, Region


class MssScreenBackend:
    """Implementacja ``ScreenBackend`` używająca biblioteki ``mss``."""

    name = "mss"

    def __init__(self) -> None:
        self._local = threading.local()

    # ------------------------------------------------------------------ internals
    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            try:
                import mss
            except ImportError as exc:  # pragma: no cover - zależność obowiązkowa
                raise BackendError("Brak biblioteki mss (pip install mss).") from exc
            sct = mss.mss()
            self._local.sct = sct
        return sct

    # ------------------------------------------------------------------ API
    def grab(self, region: Optional[Region] = None) -> np.ndarray:
        """Zwraca zrzut BGR (H x W x 3, uint8) pulpitu wirtualnego lub regionu.

        ``region=None`` oznacza CALY pulpit wirtualny (mss monitors[0]), a nie
        pierwszy monitor — przy 3 ekranach klikniecia ida wspolrzednymi
        absolutnymi wiec i szukanie musi miec pelne pole widzenia.
        """
        sct = self._sct()
        if region is None:
            monitor = sct.monitors[0]  # suma wirtualna (lewy/gorny rogi moga byc ujemne)
        else:
            x, y, w, h = region
            if w <= 0 or h <= 0:
                raise BackendError(f"Nieprawidłowy region do przechwycenia: {region}")
            monitor = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        shot = sct.grab(monitor)
        # mss zwraca BGRA (little-endian) -> odrzucamy kanał alfa.
        arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return arr[:, :, :3].copy()

    def monitors(self) -> list:
        """Fizyczne monitory (index 1..N). Główny = ten z początkiem w (0,0).

        Dotyczy Windows i X11: system zaczyna przestrzeń ekranową od rogu
        monitora głównego, a ekrany po lewej/u góry mają współrzędne ujemne.
        """
        from .base import MonitorInfo
        out = []
        for i, m in enumerate(self._sct().monitors[1:], start=1):
            region = (int(m["left"]), int(m["top"]),
                      int(m["width"]), int(m["height"]))
            out.append(MonitorInfo(index=i, region=region,
                                   is_primary=(region[0] == 0 and region[1] == 0)))
        return out

    def virtual_bounds(self) -> Region:
        m = self._sct().monitors[0]
        return (int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"]))

    def primary_size(self) -> Tuple[int, int]:
        mon = next((m for m in self.monitors() if m.is_primary), None)
        if mon is None:
            mon = self.monitors()[0]
        return mon.region[2], mon.region[3]
