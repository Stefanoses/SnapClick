"""Dopasowywanie szablonu do zrzutu ekranu (OpenCV ``matchTemplate``).

Obsługa kanału alfa szablonu jako maski — piksele przezroczyste są
ignorowane podczas szukania, co pozwala wyciąć przycisk "na miękko".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

#: Punkt (środek dopasowania) w układzie zrzutu, który dostajemy z matchTemplate
Offset = Tuple[int, int]


@dataclass(frozen=True)
class MatchResult:
    """Wynik udanego dopasowania."""

    #: Środek dopasowanego obszaru w współrzędnych obrazu źródłowego.
    center: Tuple[int, int]
    #: Lewy górny róg dopasowania.
    top_left: Tuple[int, int]
    score: float
    size: Tuple[int, int]  # (w, h) szablonu

    def center_with_offset(self, dx: int, dy: int) -> Tuple[int, int]:
        return (self.center[0] + dx, self.center[1] + dy)


def find_template(
    haystack: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.9,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[MatchResult]:
    """Szuka ``template`` w ``haystack`` (oba BGR, ewentualnie BGRA szablonu).

    Args:
        haystack: zrzut ekranu BGR (H x W x 3) lub BGRA.
        template: szablon BGR lub BGRA; kanał A potraktowany jako maska.
        threshold: minimalny score [0..1].
        region: opcjonalnie (x, y, w, h) — przeszukujemy tylko ten obszar;
            wynik jest przeliczany na współrzędne pełnego obrazu.

    Returns:
        ``MatchResult`` lub ``None`` gdy brak trafienia nad progiem.
    """
    if haystack is None or template is None:
        return None
    hay = haystack[:, :, :3] if haystack.ndim == 3 and haystack.shape[2] == 4 else haystack
    hay = np.ascontiguousarray(hay, dtype=np.uint8)

    off_x, off_y = 0, 0
    if region is not None:
        rx, ry, rw, rh = (int(v) for v in region)
        H, W = hay.shape[:2]
        rx = max(0, min(rx, W - 1))
        ry = max(0, min(ry, H - 1))
        rw = max(1, min(rw, W - rx))
        rh = max(1, min(rh, H - ry))
        hay = hay[ry:ry + rh, rx:rx + rw]
        off_x, off_y = rx, ry

    if template.ndim == 3 and template.shape[2] == 4:
        tmpl = np.ascontiguousarray(template[:, :, :3], dtype=np.uint8)
        mask = np.ascontiguousarray(template[:, :, 3], dtype=np.uint8)
        # Metoda z maską działa tylko dla TM_SQDIFF i TM_CCORR_NORMED.
        if mask.min() == mask.max() == 255:
            res = cv2.matchTemplate(hay, tmpl, cv2.TM_CCOEFF_NORMED)
        else:
            res = cv2.matchTemplate(hay, tmpl, cv2.TM_CCORR_NORMED, mask=mask)
            # TM_CCORR_NORMED z maską potrafi zwracać NaN przy zerowej wariancji.
            res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    else:
        tmpl = np.ascontiguousarray(template[:, :, :3] if template.ndim == 3 else template,
                                    dtype=np.uint8)
        # Szablon jednolity (zerowa wariancja) -> TM_CCOEFF_NORMED dalby falszywe 1.0
        if float(tmpl.astype(np.float32).std()) < 1.0:
            return None
        res = cv2.matchTemplate(hay, tmpl, cv2.TM_CCOEFF_NORMED)

    if res.size == 0:
        return None

    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None

    th, tw = tmpl.shape[:2]
    cx = off_x + max_loc[0] + tw // 2
    cy = off_y + max_loc[1] + th // 2
    return MatchResult(
        center=(cx, cy),
        top_left=(off_x + max_loc[0], off_y + max_loc[1]),
        score=float(max_val),
        size=(tw, th),
    )
