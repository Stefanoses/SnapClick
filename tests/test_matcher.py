"""Testy dopasowywania szablonów na obrazach syntetycznych."""
from __future__ import annotations

import numpy as np

from snapclick.core.vision.matcher import find_template


def make_scene(w=640, h=480) -> tuple[np.ndarray, np.ndarray]:
    """Scena z 'przyciskiem' w (300, 200) oraz szumem; zwraca (scena, szablon)."""
    rng = np.random.default_rng(42)
    scene = rng.integers(0, 60, size=(h, w, 3), dtype=np.uint8)
    # przycisk: gradientowa płytka 60x24
    patch = np.zeros((24, 60, 3), dtype=np.uint8)
    patch[:, :] = (40, 160, 240)
    patch[4:20, 6:54] = (200, 90, 30)
    x, y = 300, 200
    scene[y:y + 24, x:x + 60] = patch
    return scene, patch


def test_finds_template():
    scene, patch = make_scene()
    res = find_template(scene, patch, threshold=0.9)
    assert res is not None
    cx, cy = res.center
    assert abs(cx - (300 + 30)) <= 2 and abs(cy - (200 + 12)) <= 2
    assert res.score >= 0.99


def test_not_found_above_threshold():
    scene, _ = make_scene()
    rng = np.random.default_rng(7)
    foreign = rng.integers(0, 255, size=(24, 60, 3), dtype=np.uint8)
    assert find_template(scene, foreign, threshold=0.95) is None


def test_degenerate_flat_template_rejected():
    """Jednolity szablon nie może dawać fałszywego trafienia."""
    scene, _ = make_scene()
    flat = np.full((24, 60, 3), 255, dtype=np.uint8)
    assert find_template(scene, flat, threshold=0.5) is None


def test_region_search_and_offset():
    scene, patch = make_scene()
    # region NIE zawierający przycisku -> brak trafienia
    assert find_template(scene, patch, region=(0, 0, 200, 150)) is None
    # region zawierający, wynik w współrzędnych pełnego obrazu (bez offsetu
    # tu — interpreter sam dodaje offset gdy grabuje region)
    res = find_template(scene[200:230, 250:400], patch, threshold=0.9)
    assert res is not None
    assert res.center == (50 + 30, 12)


def test_alpha_mask_ignores_transparent_background():
    scene, patch = make_scene()
    # szablon z alfa: widoczny tylko środek patcha, krawędzie przezroczyste
    tmpl = np.dstack([patch, np.full(patch.shape[:2], 255, dtype=np.uint8)])
    tmpl[:2, :, 3] = 0
    tmpl[-2:, :, 3] = 0
    tmpl[:, :2, 3] = 0
    tmpl[:, -2:, 3] = 0
    res = find_template(scene, tmpl, threshold=0.9)
    assert res is not None
    assert res.score >= 0.9
