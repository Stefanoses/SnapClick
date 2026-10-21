"""Stan pojedynczego przebiegu scenariusza."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..platform.base import Region


@dataclass
class RunContext:
    """Flagi i dane bieżącego uruchomienia (udostępniane interpreterowi)."""

    # Twarda flaga przerwania — sprawdzana przed każdym blokiem i w pętlach.
    stop_event: threading.Event = field(default_factory=threading.Event)
    #: Region okna gry, jeśli program wskazał region="window".
    window_region: Optional[Region] = None
    #: Regiony fizycznych monitorów (index 1..N -> x,y,w,h) — wypełniane
    #: na starcie przebiegu z backendu ekranu; puste gdy backend nie
    #: wspiera enumeracji (wtedy wybór monitora degradowany jest do
    #: pulpitu wirtualnego z ostrzezeniem w logu).
    monitors: Dict[int, Region] = field(default_factory=dict)
    #: Lewy-górny róg wirtualnego pulpitu (x, y). Ujemny, gdy monitor
    #: sięga na lewo/ponad monitor główny — wtedy zrzut regionu
    #: (region=None) ZACZYNA SIĘ w tym rogu, więc przesunięcie wyniku
    #: samego regionu (x,y) nie wystarczy (były klik 1080 px za nisko).
    virtual_origin: Tuple[int, int] = (0, 0)
    #: Środek ostatnio odnalezionego elementu — bloki klik mogą go użyć.
    last_match_center: Optional[Tuple[int, int]] = None
    started_at: float = field(default_factory=time.monotonic)
    completed_blocks: int = 0

    def request_stop(self) -> None:
        self.stop_event.set()

    @property
    def stopped(self) -> bool:
        return self.stop_event.is_set()

    def sleep(self, seconds: float) -> bool:
        """Uśpienie reagujące na STOP. True = przerwane, False = dokończone."""
        if seconds <= 0:
            return self.stopped
        return self.stop_event.wait(seconds)


class BlockFailed(Exception):
    """Blok zakończył się błędem krytycznym (np. on_fail='stop')."""
