"""Definicja typów bloków (dataclasses) i metadane dla GUI/palety.

Model grafu: każdy blok ma opcjonalny wskaźnik ``next`` (kolejny w stosie).
Bloki sterujące dodatkowo:
  * ``if_found``   -> ``then`` / ``otherwise`` (głowy dwóch stosów),
  * ``while_found``/``repeat`` -> ``body`` (głowa pętli).

Pozycje ``(x, y)`` to współrzędne na canvasie GUI — silnik ich nie używa.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields, replace as _dc_replace
from enum import Enum
from typing import Any, Dict, List, Optional

from ...i18n import t


class BlockType(str, Enum):
    START = "start"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    WAIT = "wait"
    KEY_PRESS = "key_press"
    IF_FOUND = "if_found"
    WHILE_FOUND = "while_found"
    REPEAT = "repeat"


@dataclass
class Block:
    """Pojedynczy bloczek scenariusza."""

    id: str
    type: str
    x: float = 0.0
    y: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    # Wiązania grafu (identyfikatory innych bloków):
    next: Optional[str] = None
    then: Optional[str] = None
    otherwise: Optional[str] = None
    body: Optional[str] = None

    # -- pomocnicze -------------------------------------------------------
    def child_ids(self) -> List[str]:
        out = [c for c in (self.next, self.then, self.otherwise, self.body) if c]
        return out

    def param(self, name: str) -> Any:
        meta = BLOCK_META.get(self.type)
        if meta is not None and name in meta.defaults:
            return self.params.get(name, meta.defaults[name])
        return self.params.get(name)


@dataclass(frozen=True)
class ParamSpec:
    """Opis parametru — używany przez panel właściwości i walidację."""

    key: str
    label_key: str
    kind: str  # text | int | float | bool | choice | template | keycombo | region
    choices: tuple[str, ...] = ()
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    @property
    def label(self) -> str:
        """Etykieta w bieżącym języku (dynamiczna — przełączana na żywo)."""
        return t(self.label_key)


@dataclass(frozen=True)
class BlockMeta:
    """Metadane typu bloku dla edytora i interpretera."""

    type: BlockType
    label_key: str      # klucz i18n nazwy widocznej w paletcie i na bloczku
    category: str       # "events" | "actions" | "logic"
    color: int          # RGB int do zabarwienia bloczka
    shape: str          # "hat" | "stack" | "c"  (nakrywka / klocek / ramie C)
    sockets: tuple[str, ...]  # wyjścia: ("next",) / ("then","else","next") / ("body","next")
    params: tuple[ParamSpec, ...] = ()
    defaults: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return t(self.label_key)

    @property
    def category_label(self) -> str:
        return t(f"cat.{self.category}")


def _defaults(specs: tuple[ParamSpec, ...]) -> Dict[str, Any]:
    return {s.key: s.default for s in specs}


_REGION_CHOICES = ("screen", "window", "custom")

_TEMPLATE_PARAM = ParamSpec(
    "template", "param.template", "template", default="")

_THROUGHPUT_PARAMS = (
    ParamSpec("threshold", "param.threshold", "float",
              default=0.90, min_value=0.5, max_value=1.0),
    ParamSpec("timeout", "param.timeout", "float",
              default=5.0, min_value=0.0, max_value=600.0),
    ParamSpec("poll", "param.poll", "float",
              default=0.15, min_value=0.01, max_value=5.0),
)

_REGION_PARAMS = (
    ParamSpec("region", "param.region", "choice",
              choices=_REGION_CHOICES, default="screen"),
    ParamSpec("window_title", "param.window_title", "text", default=""),
    ParamSpec("custom_region", "param.custom_region", "text",
              default="0,0,0,0"),
    # Nadpisanie monitora dla regionu 'screen'. None = dziedzicz z programu
    # (pasek 'Monitor'), 0 = jawnie caly pulpit wirtualny, 1..N = konkretny.
    ParamSpec("monitor", "param.monitor", "monitor", default=None),
)

BLOCK_META: Dict[str, BlockMeta] = {
    BlockType.START.value: BlockMeta(
        type=BlockType.START, label_key="block.start.label",
        category="events", color=0xF1A328, shape="hat", sockets=("next",),
    ),
    BlockType.CLICK.value: BlockMeta(
        type=BlockType.CLICK, label_key="block.click.label",
        category="actions", color=0x4C97FF, shape="stack", sockets=("next",),
        params=(
            _TEMPLATE_PARAM,
            ParamSpec("button", "param.button", "choice",
                      choices=("left", "right", "middle"), default="left"),
            ParamSpec("double", "param.double", "bool", default=False),
            ParamSpec("focus", "param.focus", "choice",
                      choices=("auto", "on", "off"), default="auto"),
            ParamSpec("offset_x", "param.offset_x", "int", default=0),
            ParamSpec("offset_y", "param.offset_y", "int", default=0),
            *_THROUGHPUT_PARAMS,
            *_REGION_PARAMS,
            ParamSpec("post_wait", "param.post_wait_click", "float",
                      default=0.25, min_value=0.0, max_value=60.0),
            ParamSpec("on_fail", "param.on_fail", "choice",
                      choices=("stop", "continue"), default="stop"),
        ),
    ),
    BlockType.TYPE_TEXT.value: BlockMeta(
        type=BlockType.TYPE_TEXT, label_key="block.type_text.label",
        category="actions", color=0x4C97FF, shape="stack", sockets=("next",),
        params=(
            ParamSpec("text", "param.text", "text", default=""),
            ParamSpec("method", "param.method", "choice",
                      choices=("auto", "type", "clipboard", "postmessage"),
                      default="auto"),
            ParamSpec("post_wait", "param.post_wait_type", "float",
                      default=0.1, min_value=0.0, max_value=60.0),
        ),
    ),
    BlockType.WAIT.value: BlockMeta(
        type=BlockType.WAIT, label_key="block.wait.label",
        category="actions", color=0xD99E32, shape="stack", sockets=("next",),
        params=(
            ParamSpec("seconds", "param.seconds", "float",
                      default=1.0, min_value=0.0, max_value=3600.0),
        ),
    ),
    BlockType.KEY_PRESS.value: BlockMeta(
        type=BlockType.KEY_PRESS, label_key="block.key_press.label",
        category="actions", color=0x4C97FF, shape="stack", sockets=("next",),
        params=(
            ParamSpec("combo", "param.combo", "keycombo", default="enter"),
        ),
    ),
    BlockType.IF_FOUND.value: BlockMeta(
        type=BlockType.IF_FOUND, label_key="block.if_found.label",
        category="logic", color=0xFFBF4A, shape="c",
        sockets=("then", "else", "next"),
        params=(
            _TEMPLATE_PARAM,
            # IF ma wlasny (krotszy) domyslny timeout — nadpisany ponizej
            ParamSpec("threshold", "param.threshold", "float",
                      default=0.90, min_value=0.5, max_value=1.0),
            ParamSpec("timeout", "param.timeout", "float",
                      default=2.0, min_value=0.0, max_value=600.0),
            ParamSpec("poll", "param.poll", "float",
                      default=0.15, min_value=0.01, max_value=5.0),
            *_REGION_PARAMS,
        ),
    ),
    BlockType.WHILE_FOUND.value: BlockMeta(
        type=BlockType.WHILE_FOUND, label_key="block.while_found.label",
        category="logic", color=0xFFBF4A, shape="c",
        sockets=("body", "next"),
        params=(
            _TEMPLATE_PARAM,
            ParamSpec("threshold", "param.threshold", "float",
                      default=0.90, min_value=0.5, max_value=1.0),
            ParamSpec("max_iterations", "param.max_iterations", "int",
                      default=100, min_value=1, max_value=1000000),
            ParamSpec("iteration_delay", "param.iteration_delay", "float",
                      default=0.3, min_value=0.0, max_value=60.0),
            *_REGION_PARAMS,
        ),
    ),
    BlockType.REPEAT.value: BlockMeta(
        type=BlockType.REPEAT, label_key="block.repeat.label",
        category="logic", color=0xFFBF4A, shape="c", sockets=("body", "next"),
        params=(
            ParamSpec("count", "param.count", "int",
                      default=5, min_value=0, max_value=1000000),
        ),
    ),
}


def new_block(block_type: BlockType, x: float = 0.0, y: float = 0.0,
              block_id: Optional[str] = None) -> Block:
    """Tworzy blok z domyślnymi parametrami typu."""
    meta = BLOCK_META[block_type.value]
    return Block(
        id=block_id or uuid.uuid4().hex[:10],
        type=block_type.value,
        x=x, y=y,
        params=dict(meta.defaults),
    )


# Wypełnij defaults na bazie specyfikacji parametrów (raz po zdefiniowaniu).
BLOCK_META = {
    key: _dc_replace(meta, defaults=_defaults(meta.params))
    for key, meta in BLOCK_META.items()
}

# Alias dla czytelności w rejestrze
BLOCK_CLASSES = {t.value: Block for t in BlockType}
