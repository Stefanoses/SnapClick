"""Generates the example project ``examples/demo_click_loop.snapclick``.

Run:  python scripts/make_example.py
Templates are synthetic (replace them with your own screen captures).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snapclick.core.model.blocks import BlockType  # noqa: E402
from snapclick.core.model.program import Program  # noqa: E402
from snapclick.project.storage import ProjectStorage  # noqa: E402


def _label_png(text: str, w: int = 120, h: int = 40,
               bg=(60, 40, 30)) -> np.ndarray:
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (200, 180, 120), 2)
    cv2.putText(img, text, (8, h - 13), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (240, 240, 240), 1, cv2.LINE_AA)
    return img


def main() -> int:
    out_dir = ROOT / "examples"
    storage = ProjectStorage()
    storage.new_project(out_dir, "demo_click_loop")
    registry = storage.registry
    program: Program = storage.program

    for t_id, text in (("open_button", "OPEN"),
                       ("target_item", "CLICK"),
                       ("confirm_yes", "YES")):
        registry.add_from_array(t_id, _label_png(text))

    start = program.add_block(BlockType.START, 0, 0)
    open_btn = program.add_block(BlockType.CLICK, 0, 60)
    open_btn.params.update({"template": "open_button", "region": "window",
                            "post_wait": 0.8})
    wait = program.add_block(BlockType.WAIT, 0, 120)
    loop = program.add_block(BlockType.WHILE_FOUND, 0, 176)
    loop.params.update({"template": "target_item", "region": "window",
                        "max_iterations": 50, "iteration_delay": 0.4})
    click_item = program.add_block(BlockType.CLICK, 20, 220)
    click_item.params.update({"template": "target_item", "region": "window",
                              "post_wait": 0.5})
    confirm = program.add_block(BlockType.CLICK, 20, 280)
    confirm.params.update({"template": "confirm_yes", "region": "window",
                           "on_fail": "continue", "timeout": 2.0})
    end_wait = program.add_block(BlockType.WAIT, 0, 340)
    end_wait.params["seconds"] = 0.3

    program.set_socket(start.id, "next", open_btn.id)
    program.set_socket(open_btn.id, "next", wait.id)
    program.set_socket(wait.id, "next", loop.id)
    program.set_socket(loop.id, "body", click_item.id)
    program.set_socket(click_item.id, "next", confirm.id)
    program.set_socket(loop.id, "next", end_wait.id)

    problems = program.validate()
    if problems:
        print("Validation problems:", *problems, sep="\n  ")
        return 1
    path = storage.save()
    print(f"Created: {path}")
    print("Templates (synthetic!):", [m["id"] for m in registry.entries()])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
