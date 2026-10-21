"""Generates the application icon ``packaging/snapclick.png`` (256x256).

Run:  python scripts/make_icon.py

A dark rounded tile with a crosshair and a "click" ripple — reads well at
small sizes and is used by the AppImage (.DirIcon) and window icon.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging" / "snapclick.png"
SIZE = 256


def _rounded_mask(size: int, radius: int) -> np.ndarray:
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.rectangle(mask, (radius, 0), (size - radius - 1, size - 1), 255, -1)
    cv2.rectangle(mask, (0, radius), (size - 1, size - radius - 1), 255, -1)
    for cx, cy in ((radius, radius), (size - radius, radius),
                   (radius, size - radius), (size - radius, size - radius)):
        cv2.circle(mask, (cx, cy), radius, 255, -1)
    return mask


def main() -> int:
    s = SIZE
    # vertical gradient background (deep indigo -> slate)
    top = np.array([58, 42, 30], dtype=np.float32)
    bottom = np.array([24, 20, 16], dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, s, dtype=np.float32)[:, None, None]
    img = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)
    img = np.tile(img, (1, s, 1))

    white = (245, 240, 235)
    accent = (90, 200, 255)          # BGR: cyan-ish
    c = (s // 2, s // 2)

    # click ripple
    cv2.circle(img, c, int(s * 0.30), accent, int(s * 0.028), cv2.LINE_AA)
    cv2.circle(img, c, int(s * 0.19), accent, int(s * 0.022), cv2.LINE_AA)

    # crosshair
    t = max(3, int(s * 0.022))
    gap = int(s * 0.09)
    arm = int(s * 0.20)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        p1 = (c[0] + dx * gap, c[1] + dy * gap)
        p2 = (c[0] + dx * (gap + arm), c[1] + dy * (gap + arm))
        cv2.line(img, p1, p2, white, t, cv2.LINE_AA)
    cv2.circle(img, c, int(s * 0.045), white, -1, cv2.LINE_AA)

    # rounded corners
    alpha = _rounded_mask(s, int(s * 0.18)).astype(np.float32) / 255.0
    rgba = np.dstack([img, np.zeros((s, s), dtype=np.uint8)])
    rgba[:, :, 3] = (alpha * 255).astype(np.uint8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(OUT), rgba):
        raise SystemExit(f"could not write {OUT}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
