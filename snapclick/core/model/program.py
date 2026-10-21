"""Program = zbiór bloków + operacje na grafie (spójne z canvasem).

Klasa pilnuje spójności: unikalne ID, brak cykli, brak "sierot"
(blok może być wskazany przez dokładnie jedno gniazdo).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from ...i18n import t
from .blocks import BLOCK_META, Block, BlockType, new_block


class ProgramError(ValueError):
    """Nieprawidłowa operacja na grafie bloków."""


@dataclass(frozen=True)
class Problem:
    """Problem znaleziony przez walidacje.

    ``hard`` rozroznia bledy blokujace uruchomienie od ostrzezen (sieroty).
    GUI filtruje PO TYM POLU, nigdy po tresci komunikatu — tresc zalezy od
    wybranego jezyka.
    """

    message: str
    hard: bool = True


@dataclass
class Program:
    """Poziom modelu scenariusza (bez wiedzy o Qt)."""

    name: str = "Scenariusz"
    window_title: str = ""
    #: Monitor domyślny dla wyszukiwań 'screen': None = caly pulpit
    #: wirtualny, 1..N = wskazany fizyczny monitor (zgodnie z kolejnoscia
    #: backendu, tj. indeksami mss). Bloki moga go nadpisac wlasnym paramem.
    monitor: Optional[int] = None
    blocks: Dict[str, Block] = field(default_factory=dict)

    # ------------------------------------------------------------- bloki
    def add_block(self, block_type: BlockType, x: float = 0.0,
                  y: float = 0.0, block_id: Optional[str] = None) -> Block:
        if block_type is BlockType.START and self.start_block() is not None:
            raise ProgramError(t("prog.start_only_one"))
        block = new_block(block_type, x, y, block_id)
        if block.id in self.blocks:
            raise ProgramError(t("prog.dup_id", block_id=block.id))
        self.blocks[block.id] = block
        return block

    def add_existing(self, block: Block) -> Block:
        if block.id in self.blocks:
            raise ProgramError(t("prog.dup_id", block_id=block.id))
        self.blocks[block.id] = block
        return block

    def get(self, block_id: Optional[str]) -> Optional[Block]:
        return self.blocks.get(block_id) if block_id else None

    def remove_block(self, block_id: str) -> List[str]:
        """Usuwa blok wraz z całym podpiętym pod niego podgrafem.

        Zwraca listę usuniętych ID.
        """
        block = self.blocks.get(block_id)
        if block is None:
            return []
        removed: List[str] = []
        stack = [block]
        while stack:
            cur = stack.pop()
            if cur.id in removed:
                continue
            removed.append(cur.id)
            for child in (cur.next, cur.then, cur.otherwise, cur.body):
                child_block = self.blocks.get(child)
                if child_block is not None:
                    stack.append(child_block)
            # odłącz dzieci (i tak usuwane) — dla porządku
            cur.next = cur.then = cur.otherwise = cur.body = None
        for rid in removed:
            self.blocks.pop(rid, None)
            self._clear_references(rid)
        return removed

    def _clear_references(self, gone_id: str) -> None:
        for other in self.blocks.values():
            if other.next == gone_id:
                other.next = None
            if other.then == gone_id:
                other.then = None
            if other.otherwise == gone_id:
                other.otherwise = None
            if other.body == gone_id:
                other.body = None

    # ------------------------------------------------------------- graf
    def start_block(self) -> Optional[Block]:
        for b in self.blocks.values():
            if b.type == BlockType.START.value:
                return b
        return None

    def is_connected(self, block_id: str) -> bool:
        """Czy blok jest osiągalny od START (część aktywnego stosu)."""
        seen = set()
        stack: List[Optional[str]] = [
            s.id for s in self.blocks.values() if s.type == BlockType.START.value
        ]
        while stack:
            cur = stack.pop()
            while cur:
                if cur in seen:
                    break
                seen.add(cur)
                blk = self.blocks.get(cur)
                if blk is None:
                    break
                stack.extend(c for c in (blk.then, blk.otherwise, blk.body) if c)
                cur = blk.next
        return block_id in seen

    def set_socket(self, src_id: str, socket: str, dst_id: Optional[str]) -> None:
        """Podłącza ``dst`` (stos począwszy od tego bloku) do gniazda ``src.socket``.

        Jeśli ``dst`` był gdzieś indziej wpięty, zostaje najpierw odpięty
        (standardowe zachowanie edytorów blokowych — przenoszenie stosu).
        """
        if src_id == dst_id:
            raise ProgramError(t("prog.self_connect"))
        src = self.blocks.get(src_id)
        if src is None:
            raise ProgramError(t("prog.no_src", block_id=src_id))
        meta = BLOCK_META.get(src.type)
        if meta is None or socket not in meta.sockets:
            raise ProgramError(
                t("prog.no_socket", block_type=src.type, socket=socket))

        attr = {"next": "next", "then": "then", "else": "otherwise",
                "body": "body"}[socket]

        if dst_id is not None:
            dst = self.blocks.get(dst_id)
            if dst is None:
                raise ProgramError(t("prog.no_dst", block_id=dst_id))
            # cykl? dst nie może być przodkiem src
            if self._reaches(dst_id, src_id):
                raise ProgramError(t("prog.cycle"))
            # odpięcie dst od obecnego rodzica
            for other in self.blocks.values():
                for a in ("next", "then", "otherwise", "body"):
                    if getattr(other, a) == dst_id:
                        setattr(other, a, None)
            # wpięcie: nadpisuje stare dziecko gniazda (stos przeniesiony)
            setattr(src, attr, dst_id)
        else:
            setattr(src, attr, None)

    def _reaches(self, from_id: str, target_id: str) -> bool:
        """Czy z bloku ``from_id`` (przez wszystkie gniazda) osiągalny jest target."""
        seen = set()
        stack = [from_id]
        while stack:
            cur = stack.pop()
            if cur == target_id:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            blk = self.blocks.get(cur)
            if blk:
                stack.extend(blk.child_ids())
        return False

    # ------------------------------------------------------------ walidacja
    def validate_problems(self) -> List[Problem]:
        """Problemy grafu z klasyfikacja hard/soft (GUI filtrowie po ``hard``)."""
        problems: List[Problem] = []
        if self.start_block() is None:
            problems.append(Problem(t(
                "validate.no_start",
                label=BLOCK_META[BlockType.START.value].label)))

        # unikalność rodzica + istnienie wskazań
        parents: Dict[str, List[str]] = {}
        for b in self.blocks.values():
            meta = BLOCK_META.get(b.type)
            if meta is None:
                problems.append(Problem(
                    t("validate.unknown_type", block_id=b.id,
                      block_type=b.type)))
                continue
            for socket, child in (("next", b.next), ("then", b.then),
                                  ("else", b.otherwise), ("body", b.body)):
                if child is None:
                    continue
                if socket not in meta.sockets:
                    problems.append(Problem(t(
                        "validate.no_socket", label=meta.label,
                        block_id=b.id, socket=socket)))
                if child not in self.blocks:
                    problems.append(Problem(t(
                        "validate.dangling", block_id=b.id, child=child)))
                else:
                    parents.setdefault(child, []).append(f"{b.id}:{socket}")
        for child, ps in parents.items():
            if len(ps) > 1:
                problems.append(Problem(
                    t("validate.multi_parent", child=child,
                      sockets=", ".join(ps))))

        # cykle przez DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {bid: WHITE for bid in self.blocks}

        def visit(bid: str) -> bool:
            color[bid] = GRAY
            blk = self.blocks[bid]
            for c in blk.child_ids():
                if c not in color:
                    continue
                if color[c] == GRAY:
                    problems.append(
                        Problem(t("validate.cycle_detected", block_id=c)))
                    return True
                if color[c] == WHITE and not visit(c):
                    return True
            color[bid] = BLACK
            return False

        for bid in list(self.blocks):
            if color[bid] == WHITE:
                visit(bid)

        # sieroty (poza START) — ostrzeżenie miękkie, raportujemy
        for b in self.blocks.values():
            if b.type == BlockType.START.value:
                continue
            if b.id not in parents and self.blocks:
                problems.append(Problem(
                    t("validate.orphan",
                      label=BLOCK_META[b.type].label, block_id=b.id),
                    hard=False))
        return problems

    def validate(self) -> List[str]:
        """Zwraca listę komunikatów o problemach (pusta = OK)."""
        return [p.message for p in self.validate_problems()]

    # ------------------------------------------------------- przejścia
    def execution_order(self) -> Iterable[Block]:
        """Iterator bloków w kolejności wykonania (do podglądu)."""
        start = self.start_block()
        if start is None:
            return []
        return self._walk(start)

    def _walk(self, start: Block) -> Iterable[Block]:
        out: List[Block] = []
        seen = set()

        def walk(bid: Optional[str]) -> None:
            while bid:
                blk = self.blocks.get(bid)
                if blk is None or bid in seen:
                    return
                seen.add(bid)
                out.append(blk)
                for child in (blk.then, blk.otherwise, blk.body):
                    if child:
                        walk(child)
                bid = blk.next

        walk(start.id)
        return out
