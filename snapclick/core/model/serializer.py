"""Serializacja ``Program`` <-> słownik JSON (format pliku ``.snapclick``).

Format::

    {
      "schema": 1,
      "name": "...",
      "window_title": "",
      "monitor": null | 1..N,
      "templates": [{"id": "...", "file": "assets/....png"}, ...],
      "blocks": [
        {"id": "b1", "type": "click", "x": 40, "y": 40,
         "params": {...}, "next": "b2", "then": null, "else": null, "body": null}
      ]
    }
"""
from __future__ import annotations

from typing import Any, Dict

from .blocks import BLOCK_META, Block
from .program import Program

SCHEMA_VERSION = 1


def program_to_dict(program: Program,
                    templates: list[dict] | None = None) -> Dict[str, Any]:
    """Model -> surowy słownik (do ``json.dump``)."""
    blocks_out = []
    for b in program.blocks.values():
        entry: Dict[str, Any] = {
            "id": b.id,
            "type": b.type,
            "x": b.x,
            "y": b.y,
            "params": dict(b.params),
        }
        if b.next:
            entry["next"] = b.next
        if b.then:
            entry["then"] = b.then
        if b.otherwise:
            entry["else"] = b.otherwise
        if b.body:
            entry["body"] = b.body
        blocks_out.append(entry)
    return {
        "schema": SCHEMA_VERSION,
        "name": program.name,
        "window_title": program.window_title,
        "monitor": program.monitor,
        "templates": list(templates or []),
        "blocks": blocks_out,
    }


def load_program_dict(data: Dict[str, Any]) -> tuple[Program, list[dict]]:
    """Słownik JSON -> ``(Program, templates)``. Waliduje typy i gniazda."""
    version = data.get("schema")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Nieznana wersja formatu projektu: {version!r} "
            f"(oczekiwano {SCHEMA_VERSION}).")

    raw_monitor = data.get("monitor")
    try:
        monitor = int(raw_monitor) if raw_monitor not in (None, "") else None
    except (TypeError, ValueError):
        monitor = None

    program = Program(
        name=str(data.get("name", "Scenariusz")),
        window_title=str(data.get("window_title", "")),
        monitor=monitor,
    )

    # bloki najpierw w całości, potem wiązania (kolejność w pliku dowolna)
    raw_blocks = data.get("blocks", [])
    for raw in raw_blocks:
        btype = str(raw.get("type", ""))
        if btype not in BLOCK_META:
            raise ValueError(f"Nieznany typ bloku: {btype!r}")
        meta = BLOCK_META[btype]
        params = {k: v for k, v in dict(raw.get("params", {})).items()
                  if k in meta.defaults}
        block = Block(
            id=str(raw["id"]),
            type=btype,
            x=float(raw.get("x", 0.0)),
            y=float(raw.get("y", 0.0)),
            params=params,
            next=raw.get("next"),
            then=raw.get("then"),
            otherwise=raw.get("else"),
            body=raw.get("body"),
        )
        program.add_existing(block)

    # sanity-check wskazanych identyfikatorów
    for b in program.blocks.values():
        for socket, child in (("next", b.next), ("then", b.then),
                              ("else", b.otherwise), ("body", b.body)):
            if child and child not in program.blocks:
                raise ValueError(
                    f"Blok {b.id} wskazuje na nieistniejący blok '{child}' "
                    f"w gnieździe '{socket}'.")

    templates = list(data.get("templates", []))
    return program, templates
