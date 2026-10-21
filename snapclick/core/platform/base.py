"""Abstrakcja warstwy platformowej.

Silnik (interpreter) oraz GUI rozmawiają wyłącznie z tymi protokołami.
Implementacje: ``win32`` (Windows 11) i ``x11`` (Linux + X11).
Dzięki temu testy mogą wstrzykiwać moki bez ekranu i myszy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple

#: Region ekranu w pikselach fizycznych: (x, y, szerokość, wysokość).
Region = Tuple[int, int, int, int]


class BackendError(RuntimeError):
    """Backend platformowy niedostępny lub operacja niemożliwa."""


@dataclass(frozen=True)
class PlatformInfo:
    """Wynik autodetekcji środowiska uruchomieniowego."""

    os_name: str  # "windows" | "linux" | "unknown"
    session: str  # "windows" | "x11" | "wayland" | "none"
    display: Optional[str] = None

    @property
    def is_windows(self) -> bool:
        return self.os_name == "windows"

    @property
    def is_linux_x11(self) -> bool:
        return self.os_name == "linux" and self.session == "x11"


@dataclass(frozen=True)
class WindowInfo:
    """Okno aplikacji widoczne dla systemu (do celowania regionem szukania)."""

    window_id: int
    title: str
    region: Region
    is_visible: bool


@dataclass(frozen=True)
class MonitorInfo:
    """Fizyczny monitor w wirtualnym pulpicie (współrzędne pikseli fizycznych).

    ``index`` to stabilne 1-based oznaczenie używane w projektach i UI
    (0 = „auto" zarezerwowane wyżej — tu nigdy nie występuje). ``region`` to
    prostokąt monitora w przestrzeni wirtualnego pulpitu — na Windows i X11
    główny monitor ma początek w (0,0), a monitory po lewej/u góry mają
    współrzędne ujemne.
    """

    index: int
    region: Region
    is_primary: bool = False

    @property
    def label(self) -> str:
        """Surowa (językowo neutralna) etykieta: 1920x1080+0+0."""
        x, y, w, h = self.region
        return f"{w}x{h}+{x}+{y}"


class ScreenBackend(Protocol):
    """Przechwytywanie obrazu ekranu. Zwraca tablicę numpy BGR (H x W x 3)."""

    def grab(self, region: Optional[Region] = None) -> Any:
        """Zrzut wirtualnego pulpitu (region=None) albo jego fragmentu."""
        ...

    def monitors(self) -> list:
        """Fizyczne monitory jako ``list[MonitorInfo]`` (index 1..N)."""
        ...

    def virtual_bounds(self) -> Region:
        """Prostokąt wirtualnego pulpitu (suma wszystkich monitorów)."""
        ...

    def primary_size(self) -> Tuple[int, int]:
        """Rozmiar głównego monitora (szerokość, wysokość) w pikselach fizycznych."""
        ...


class WindowBackend(Protocol):
    """Enumeracja i aktywacja okien systemowych."""

    def list_windows(self) -> list[WindowInfo]:
        ...

    def find_region(self, title_substr: str) -> Optional[Region]:
        """Region pierwszego widocznego okna z podstringiem w tytule."""
        ...

    def activate(self, title_substr: str) -> bool:
        """Przywołanie okna na wierzch. Zwraca True gdy się udało."""
        ...


class InputBackend(Protocol):
    """Wstrzykiwanie zdarzeń myszy i klawiatury."""

    def move(self, x: int, y: int) -> None:
        ...

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        ...

    def press_combo(self, combo: str) -> None:
        """Combo typu ``ctrl+v`` lub pojedynczy klawisz ``esc``."""
        ...

    def type_text(self, text: str, method: str = "auto") -> None:
        """Wpisanie tekstu. method: auto | type | clipboard."""
        ...

    def set_clipboard(self, text: str) -> None:
        ...
