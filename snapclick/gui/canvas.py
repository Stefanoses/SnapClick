"""Canvas bloczków à la Scratch na QGraphicsView.

Model (``Program``) jest jedynym źródłem prawdy: ``BlockItem`` jedynie
renderuje ``Block``. Pozycje bloków połączonych wywodzone są z gniazd
rodzica (relayout), sieroty (korzenie) swobodnie "pływają".
"""
from __future__ import annotations

import shiboken6  # isValid(): ochrona przed martwymi obiektami C++ w rozbiórce
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsObject, QGraphicsScene,
                               QGraphicsView, QApplication, QMenu)

from ..core.model.blocks import BLOCK_META, Block, BlockMeta
from ..core.model.program import Program, ProgramError
from ..i18n import t
from . import theme

# ---------------------------------------------------------------- geometria
ARM_W = 18          # szerokość lewego ramienia bloku C
ROUNDED = 9         # zaokraglenie naroznikow (styl dark-mode)
HAT_CAP_R = 24      # promyk "czapki" klocka START
HAT_H = 52          # nakrywka START (zaokrąglona góra)
STACK_H = 56        # klocek prosty: etykieta + podsumowanie parametrow
C_HEADER_H = 34     # gorny pasek bloku C (etykieta)
MIDDLE_H = 28       # pasek "W INNYM PRZYPADKU"
FOOT_H = 16
MOUTH_MIN = 44      # minimalna głębokosc wneki
GRID = 8
SNAP_DIST = 26

_FONT = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
_FONT_SMALL = QFont("Segoe UI", 9)
_FONT_TAB = QFont("Segoe UI", 8, QFont.Weight.Bold)


def _color(meta: BlockMeta, factor: float = 1.0) -> QColor:
    """Wypelnienie klocka — kolor typu dociety do ciemnego UI (temat)."""
    return theme.block_fill(meta.color, factor)


def params_summary(block: Block) -> str:
    """Krótka etykieta parametrow widoczna na klocku (jezyk UI)."""
    parts: List[str] = []
    for spec in BLOCK_META[block.type].params:
        value = block.param(spec.key)
        if spec.kind == "template" and value:
            parts.append(t("summary.image", value=value))
        elif spec.key == "text" and value:
            text = str(value)
            parts.append(f"'{text[:18]}'" + ("…" if len(text) > 18 else ""))
        elif spec.key == "seconds" and value is not None:
            parts.append(f"{value} s")
        elif spec.key == "count" and value is not None:
            parts.append(f"{value}x")
        elif spec.key == "combo" and value:
            parts.append(str(value))
        elif spec.key == "button" and value not in ("left",):
            parts.append({"right": t("summary.right"),
                          "middle": t("summary.middle")}.get(str(value), ""))
    return " · ".join(p for p in parts if p)


# --------------------------------------------------------------- layout
class Layout:
    """Oblicza wymiary i pozycje gniazd na bazie modelu (bez Qt)."""

    def __init__(self, program: Program) -> None:
        self.program = program

    def own_height(self, block: Block) -> float:
        meta = BLOCK_META[block.type]
        if meta.shape == "hat":
            return HAT_H
        if meta.shape != "c":
            return STACK_H
        h = C_HEADER_H + self._mouth_h(block, block.body or block.then) \
            + FOOT_H
        if "else" in meta.sockets:
            h += MIDDLE_H + self._mouth_h(block, block.otherwise)
        return float(h)

    def _mouth_h(self, block: Block, head_id: Optional[str]) -> float:
        return max(MOUTH_MIN, self.stack_height(head_id)) if head_id else MOUTH_MIN

    def stack_height(self, head_id: Optional[str]) -> float:
        total, seen = 0.0, set()
        cur = head_id
        while cur and cur not in seen:
            seen.add(cur)
            blk = self.program.get(cur)
            if blk is None:
                break
            total += self.own_height(blk)
            cur = blk.next
        return total

    def socket_pos(self, block: Block, socket: str) -> Tuple[float, float]:
        """Pozycja (lewy górny róg wtyczki) gniazda względem bloku + jego pozycja."""
        x, y = block.x, block.y
        meta = BLOCK_META[block.type]
        if socket == "next":
            return (x, y + self.own_height(block))
        if socket in ("then", "body"):
            return (x + ARM_W, y + C_HEADER_H)
        if socket == "else":
            mouth1 = self._mouth_h(block, block.body or block.then)
            return (x + ARM_W, y + C_HEADER_H + mouth1 + MIDDLE_H)
        raise KeyError(socket)

    def sockets(self, block: Block) -> Iterable[Tuple[str, Tuple[float, float]]]:
        for s in BLOCK_META[block.type].sockets:
            yield s, self.socket_pos(block, s)

    def mouth_rects(self, block: Block) -> List[QRectF]:
        """Wnetrza blokow C (do odjecia w shape)."""
        meta = BLOCK_META[block.type]
        if meta.shape != "c":
            return []
        out = []
        x, y = block.x, block.y
        m1 = self._mouth_h(block, block.body or block.then)
        out.append(QRectF(x + ARM_W, y + C_HEADER_H,
                          self.mouth_width(block), m1))
        if "else" in meta.sockets:
            m2 = self._mouth_h(block, block.otherwise)
            out.append(QRectF(x + ARM_W, y + C_HEADER_H + m1 + MIDDLE_H,
                              self.mouth_width(block), m2))
        return out

    def _content_width(self, block: Block) -> float:
        w = self.text_width(block) - ARM_W
        for head in (block.body or block.then, block.otherwise, block.next):
            cur = head
            while cur:
                blk = self.program.get(cur)
                if blk is None:
                    break
                w = max(w, self.text_width(blk))
                cur = blk.next
        return w

    def mouth_width(self, block: Block) -> float:
        """Szerokosc wnetrza (otwartej 'polki') bloku C."""
        return max(self._content_width(block), 120.0)

    @staticmethod
    def text_width(block: Block) -> float:
        meta = BLOCK_META[block.type]
        label = meta.label
        summary = params_summary(block)
        w = max(len(label), len(summary)) * 7.5 + 32
        return max(150.0, w)

    def block_rect(self, block: Block) -> QRectF:
        meta = BLOCK_META[block.type]
        if meta.shape == "c":
            # caly obrys = lewe ramie + wnka; prawy brzeg wnki dokladnie
            # pokrywa sie z prawym brzegiem bloku (zadnych 'polek' na zewnatrz)
            w = ARM_W + self.mouth_width(block)
        else:
            w = self.text_width(block)
        return QRectF(block.x, block.y, w, self.own_height(block))


# ----------------------------------------------------------------- item
class BlockItem(QGraphicsObject):
    """Graficzna reprezentacja bloku (rysuje ksztalt + etykiety)."""

    def __init__(self, block: Block, layout: Layout) -> None:
        super().__init__()
        self.block = block
        self.layout = layout
        self.meta = BLOCK_META[block.type]
        self.active = False       # podswietlenie: silnik wykonuje ten blok
        self.setPos(block.x, block.y)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        # Bez ItemIsSelectable setSelected() jest bezskuteczne — a na
        # isSelected() opiera sie podswietlenie i usuwanie (Delete/menu).
        self.setFlags(self.flags()
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    # -- geometry ------------------------------------------------------
    def boundingRect(self) -> QRectF:
        w, h = self._local_size()
        # zapas na cień i pogrubiony obrys (active/selected)
        return QRectF(0, 0, w, h).adjusted(-5, -5, 5, 9)

    def refresh_geometry(self) -> None:
        """Po zmianie parametrow (inny tekst => inny obrys)."""
        self.prepareGeometryChange()
        self.update()

    # -- sciezki ksztaltu ----------------------------------------------
    @staticmethod
    def _rounded_body(rect: QRectF, top_r: float, bottom_r: float) -> QPainterPath:
        """Obrys klocka: gora i dol o roznym zaokragleniu (czapka START)."""
        top_r = min(top_r, rect.width() / 2, rect.height() / 2)
        bottom_r = min(bottom_r, rect.width() / 2, rect.height() / 2)
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        path = QPainterPath()
        path.moveTo(x + top_r, y)
        path.lineTo(x + w - top_r, y)
        path.quadTo(x + w, y, x + w, y + top_r)
        path.lineTo(x + w, y + h - bottom_r)
        path.quadTo(x + w, y + h, x + w - bottom_r, y + h)
        path.lineTo(x + bottom_r, y + h)
        path.quadTo(x, y + h, x, y + h - bottom_r)
        path.lineTo(x, y + top_r)
        path.quadTo(x, y, x + top_r, y)
        path.closeSubpath()
        return path

    def body_path(self) -> QPainterPath:
        """Zewnetrzny obrys (bez wnetrz blokow C) — slzy do obrysu i cienia."""
        rect = QRectF(0, 0, *self._local_size())
        top = HAT_CAP_R if self.meta.shape == "hat" else ROUNDED
        return self._rounded_body(rect, top, ROUNDED)

    def shape(self) -> QPainterPath:
        """Kszalt trafien/wypelnienia: obrys minus wnetrza blokow C."""
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addPath(self.body_path())
        # wnetrza odjete jako otwory z zaokragleniem tylko po prawej stronie;
        # ich prawy brzeg pokrywa sie z krawedzia bloku (patrz Layout), wiec
        # klocek C ma otwarta 'polke' zamiast zamknietego pudla
        for mouth in self.layout.mouth_rects(self.block):
            path.addPath(self._mouth_hole(
                mouth.translated(-self.block.x, -self.block.y)))
        return path

    @staticmethod
    def _mouth_hole(m: QRectF) -> QPainterPath:
        """Otwor wneki: lewe narozniki proste (ramie), prawe zaokraglone."""
        r = ROUNDED - 2
        p = QPainterPath()
        p.moveTo(m.x(), m.y())
        p.lineTo(m.right() - r, m.y())
        p.quadTo(m.right(), m.y(), m.right(), m.y() + r)
        p.lineTo(m.right(), m.bottom() - r)
        p.quadTo(m.right(), m.bottom(), m.right() - r, m.bottom())
        p.lineTo(m.x(), m.bottom())
        p.closeSubpath()
        return p

    def _local_size(self) -> Tuple[float, float]:
        rect = self.layout.block_rect(self.block)
        return rect.width(), rect.height()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N803
        meta = BLOCK_META[self.block.type]
        self_meta = meta  # skrót dla czytelności poniżej
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = _color(self_meta)
        body = self.body_path()
        shape = self.shape()

        # miekki cień pod blockiem (głebia na ciemnym tle)
        shadow = QColor(0, 0, 0, 70)
        painter.translate(0, 2.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawPath(body)
        painter.translate(0, -2.5)

        # wypelnienie: pionowy gradient (gora jaśniejsza ~5%)
        _, h = self._local_size()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, fill.lighter(110))
        grad.setColorAt(1.0, fill)
        painter.setBrush(QBrush(grad))

        # obrys: kolor kategorii; active/selected — grubszy i jasniejszy
        if self.active:
            pen = QPen(QColor(theme.ACCENT_MARK), 2.4)
        elif self.isSelected():
            pen = QPen(QColor(theme.ACCENT), 2.0)
        else:
            pen = QPen(theme.block_border(fill), 1.4)
        painter.setPen(pen)
        painter.drawPath(shape)

        w, _ = self._local_size()
        text_x = ARM_W + 8 if self_meta.shape == "c" else 14
        text_w = max(w - text_x - 10, 40)
        # etykieta
        painter.setPen(QPen(QColor(theme.BLOCK_TEXT)))
        painter.setFont(_FONT)
        top_pad = 16 if self_meta.shape == "hat" else 9
        label_rect = QRectF(text_x, top_pad, text_w, 18)
        painter.drawText(label_rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self_meta.label)
        # podsumowanie parametrow
        summary = params_summary(self.block)
        if summary:
            painter.setPen(QPen(QColor(theme.BLOCK_TEXT_DIM)))
            painter.setFont(_FONT_SMALL)
            sum_rect = QRectF(text_x, top_pad + 19, text_w, 15)
            painter.drawText(sum_rect,
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             summary)
        # etykieta gniazda else — subtelny, letter-spaced napis
        if "else" in self_meta.sockets:
            y_else = C_HEADER_H + self.layout._mouth_h(
                self.block, self.block.body or self.block.then) + 6
            painter.setPen(QPen(QColor(theme.TEXT_MUTED)))
            painter.setFont(_FONT_TAB)
            painter.drawText(QRectF(text_x, y_else, max(w - text_x - 10, 60), 16),
                             Qt.AlignmentFlag.AlignLeft, t("canvas.else_label"))
        # gniazda 'then'/'body'/'else' jako subtelna, akcentowa kreska
        if any(s in ("then", "body", "else")
               for s in self_meta.sockets):
            painter.setPen(QPen(theme.block_accent(fill), 2.4))
            painter.drawLine(ARM_W, C_HEADER_H - 6,
                             ARM_W, C_HEADER_H + 6)
            if "else" in self_meta.sockets:
                y_else = C_HEADER_H + self.layout._mouth_h(
                    self.block, self.block.body or self.block.then) \
                    + MIDDLE_H
                painter.drawLine(ARM_W, y_else - 6, ARM_W, y_else + 6)


# ----------------------------------------------------------------- canvas
class BlockCanvas(QGraphicsView):
    """Edytor graficzny; sygnalizuje zmiany do paneli i okna glownego."""

    block_selected = Signal(object)        # Optional[str] — id lub None
    program_changed = Signal()             # struktura/parametry sie zmienily
    status_message = Signal(str)

    MIME_BLOCK = "application/x-m2-blocktype"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # Ciemna, nie czarna scena — spójna z reszta UI
        self.setBackgroundBrush(QBrush(QColor(theme.SCENE_BG)))
        self.setAcceptDrops(True)
        # StrongFocus: QGraphicsView domyslnie przejmuje fokus tylko Tabem/
        # kolkiem, wiec klawisz Delete nigdy nie trafial do widoku.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._program: Optional[Program] = None
        self._layout: Optional[Layout] = None
        self.items: Dict[str, BlockItem] = {}

        # stan przeciągania
        self._drag_head: Optional[str] = None
        self._drag_subtree: List[str] = []
        self._drag_start_scene: Optional[QPointF] = None
        self._drag_offsets: Dict[str, QPointF] = {}
        self._dragging = False
        self._snap_target: Optional[Tuple[str, str]] = None
        self._found_marker: Optional[Tuple[int, int]] = None
        self._active_block: Optional[str] = None
        # Usuniete itemy trzymane do nastepnej iteracji petli zdarzen —
        # patrz _dispose_item().
        self._dying: List[BlockItem] = []

    # ----------------------------------------------------------- model
    def set_program(self, program: Program) -> None:
        if self._program is not program:
            for item in self.items.values():
                self._dispose_item(item)
            self.items.clear()
        self._program = program
        self._layout = Layout(program)
        self.refresh()

    @property
    def program(self) -> Program:
        assert self._program is not None, "canvas nie podłączony do programu"
        return self._program

    def refresh(self) -> None:
        """Synchronizuje itemy z modelem (po load/usunięciach itp.)."""
        program = self.program
        assert self._layout is not None
        for gone in [bid for bid in self.items if bid not in program.blocks]:
            self._dispose_item(self.items.pop(gone))
        for bid, block in program.blocks.items():
            if bid not in self.items:
                item = BlockItem(block, self._layout)
                self.scene.addItem(item)
                self.items[bid] = item
            else:
                self.items[bid].refresh_geometry()
        self.layout_all()

    def _dispose_item(self, item: BlockItem) -> None:
        """Odklada usuniecie itema poza biezacy dispatch zdarzen Qt.

        Usuniecie bloku nastepuje ZAWSZE wewnatrz dispatchu, ktory trzyma
        surowe wskazniki do itemow sceny (contextMenuEvent + menu.exec,
        mouseReleaseEvent z pressItem, hoverItems, stan panelu). Natychmiastowa
        destrukcja obiektu C++ (removeItem + GC wrappera) = use-after-free,
        ktory Windows kwituje fast-failem 0xC0000409 bez pythonowego
        tracebacka — i ktory manifestuje sie dopiero od pewnej liczby
        usuwanych itemow (podgraf wiekszy niz 1 blok), bo to classic
        niezdeterministyczne UB.

        Dlatego tutaj NIE dotykamy obiektu C++: item zostaje w scenie, ale
        staje sie niewidoczny/nieaktywny/niezaznaczalny (nie bierze udzialu
        w hit-testingu ani repaint). Realne usuniecie nastepni w
        _release_dying() — w czystym tyku petli zdarzen, kiedy zadne
        natywne wskazniki nie wskazuja juz na biezacy stos wyolan.
        """
        item.setSelected(False)
        item.setEnabled(False)
        item.setVisible(False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._dying.append(item)
        QTimer.singleShot(0, self._release_dying)

    def _release_dying(self) -> None:
        """Naprawde usuwa odlozone itemy, gdy nie ma aktywnego popupu ani
        wciśniętego przycisku myszy (menu kontekstowe kreci ZGNIEZDZONA petle
        zdarzen — singleShot(0) moglby odpalic, gdy na stosie wciaz lezy
        dispatch contextMenuEvent/mouseReleaseEvent).

        removeItem() w czystym tyku + deleteLater(): Qt'owy, udokumentowany
        bezpieczny wzorzec niszczenia elementow sceny, ktore mogly byc
        wskazane przez biezace zdarzenia.
        """
        if not self._dying:
            return
        app = QApplication.instance()
        if (app is not None
                and (app.activePopupWidget() is not None
                     or app.mouseButtons() != Qt.MouseButton.NoButton)):
            QTimer.singleShot(100, self._release_dying)
            return
        dying, self._dying = self._dying, []
        for item in dying:
            self.scene.removeItem(item)
            item.deleteLater()

    # ---------------------------------------------------------- layout
    def relayout_from(self, head_id: str) -> None:
        """Ustawia pozycje bloków podporządkowanych (zagnieżdżonych)."""
        assert self._layout is not None
        seen: set[str] = set()

        def place(bid: str) -> None:
            if bid in seen:
                return
            seen.add(bid)
            blk = self.program.get(bid)
            if blk is None:
                return
            if bid in self.items and shiboken6.isValid(self.items[bid]):
                self.items[bid].setPos(blk.x, blk.y)
            for socket, child in (("next", blk.next), ("then", blk.then),
                                  ("else", blk.otherwise), ("body", blk.body)):
                if not child:
                    continue
                sx, sy = self._layout.socket_pos(blk, socket)
                child_blk = self.program.get(child)
                if child_blk is not None:
                    child_blk.x, child_blk.y = sx, sy
                    place(child)

        place(head_id)

    def layout_all(self) -> None:
        assert self._layout is not None
        # po przełączeniu języka layout_all bywa wołany gdy okno jest w trakcie
        # destrukcji (deleteLater w teście/aplikacji) — C++ side bywa już
        # martwy choć pythonowe referencje żyją; guard zapobiega RuntimeError
        for root in self._roots():
            self.relayout_from(root)
        for bid, item in self.items.items():
            if not shiboken6.isValid(item):
                continue
            blk = self.program.get(bid)
            if blk is not None:
                item.setPos(blk.x, blk.y)
                item.update()
        self._update_scene_rect()

    def _roots(self) -> List[str]:
        child_ids = {c for b in self.program.blocks.values() for c in b.child_ids()}
        return [bid for bid in self.program.blocks if bid not in child_ids]

    def _update_scene_rect(self) -> None:
        rect = QRectF(-2000, -2000, 4000, 4000)
        for item in self.items.values():
            if shiboken6.isValid(item):
                rect = rect.united(QRectF(item.x(), item.y(), 400, 200))
        self.setSceneRect(rect)

    # ------------------------------------------------- podświetlenia
    def retranslate(self) -> None:
        """Po zmianie jezyka: bloki same rysuja etykiety przez i18n, wiec
        wystarcza recalculacja obrysow (etykiety PL/EN maja inne szerokosci)
        i repaint."""
        self.layout_all()

    def set_active_block(self, block_id: Optional[str]) -> None:
        if self._active_block and self._active_block in self.items:
            self.items[self._active_block].active = False
            self.items[self._active_block].update()
        self._active_block = block_id
        if block_id and block_id in self.items:
            self.items[block_id].active = True
            self.items[block_id].update()
            self.ensureVisible(self.items[block_id])

    def set_found_marker(self, center: Optional[Tuple[int, int]]) -> None:
        self._found_marker = center
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._found_marker:
            x, y = self._found_marker
            painter.setPen(QPen(QColor(theme.ACCENT_MARK), 2))
            painter.drawEllipse(QPointF(x, y), 10, 10)
            painter.drawLine(QPointF(x - 16, y), QPointF(x - 4, y))
            painter.drawLine(QPointF(x + 4, y), QPointF(x + 16, y))
            painter.drawLine(QPointF(x, y - 16), QPointF(x, y - 4))
            painter.drawLine(QPointF(x, y + 4), QPointF(x, y + 16))

    # ------------------------------------------------------- mysz/drag
    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        block_item = self._block_item(item)
        if event.button() == Qt.MouseButton.LeftButton and block_item:
            bid = block_item.block.id
            self._begin_drag(bid, self.mapToScene(event.position().toPoint()))
            event.accept()
            # nie wywolujemy super() — sami przejmujemy fokus, zeby
            # klawisz Delete trafil do keyPressEvent tego widoku
            self.setFocus()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.scene.clearSelection()
            self.block_selected.emit(None)
        super().mousePressEvent(event)

    @staticmethod
    def _block_item(item) -> Optional[BlockItem]:
        while item is not None and not isinstance(item, BlockItem):
            item = item.parentItem()
        return item  # type: ignore[return-value]

    def _subtree(self, head_id: str) -> List[str]:
        out, seen = [], set()
        stack = [head_id]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            blk = self.program.get(cur)
            if blk is None:
                continue
            out.append(cur)
            stack.extend(blk.child_ids())
        return out

    def _begin_drag(self, head_id: str, scene_pos: QPointF) -> None:
        self._drag_head = head_id
        self._drag_subtree = self._subtree(head_id)
        self._drag_start_scene = scene_pos
        self._drag_offsets = {}
        for bid in self._drag_subtree:
            blk = self.program.get(bid)
            if blk is not None:
                self._drag_offsets[bid] = QPointF(blk.x, blk.y) - scene_pos
        self._dragging = False
        # zaznacz caly sciagany stos
        self.scene.clearSelection()
        for bid in self._drag_subtree:
            self.items[bid].setSelected(True)
        self.block_selected.emit(head_id)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_head is None:
            super().mouseMoveEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if not self._dragging and (scene_pos - self._drag_start_scene).manhattanLength() > 4:
            self._dragging = True
        if self._dragging:
            self._snap_target = self._find_snap(scene_pos)
            head = self.program.get(self._drag_head) if self._drag_head else None
            if head is not None:
                if self._snap_target is not None:
                    self._place_subtree_at_socket(self._snap_target, scene_pos)
                else:
                    head.x, head.y = scene_pos.x(), scene_pos.y()
                    self.relayout_from(self._drag_head)
            self.viewport().update()
        event.accept()

    def _place_subtree_at_socket(self, target: Tuple[str, str],
                                 scene_pos: QPointF) -> None:
        assert self._layout is not None and self._drag_head
        parent = self.program.get(target[0])
        if parent is None:
            return
        sx, sy = self._layout.socket_pos(parent, target[1])
        head = self.program.get(self._drag_head)
        if head is None:
            return
        head.x, head.y = sx, sy
        self.relayout_from(self._drag_head)

    def _find_snap(self, head_pos: QPointF) -> Optional[Tuple[str, str]]:
        """Nearest socket (outside dragged subtree) for dragged head."""
        assert self._layout is not None
        head_id = self._drag_head
        assert head_id is not None
        head = self.program.get(head_id)
        if head is None or BLOCK_META[head.type].shape == "hat":
            return None  # START nie wpina sie w gniazda
        best: Optional[Tuple[float, Tuple[str, str]]] = None
        for bid, blk in self.program.blocks.items():
            if bid in self._drag_subtree:
                continue
            for socket, (sx, sy) in self._layout.sockets(blk):
                dist = ((sx - head_pos.x()) ** 2 + (sy - head_pos.y()) ** 2) ** 0.5
                if dist < SNAP_DIST and (best is None or dist < best[0]):
                    best = (dist, (bid, socket))
        return best[1] if best else None

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_head is None:
            super().mouseReleaseEvent(event)
            return
        head_id, target, dragging = self._drag_head, self._snap_target, self._dragging
        self._drag_head = self._snap_target = None
        scene_pos = self.mapToScene(event.position().toPoint())
        if dragging:
            try:
                if target is not None:
                    self._connect(head_id, target)
                else:
                    self._detach(head_id)
                    head = self.program.get(head_id)
                    if head is not None and BLOCK_META[head.type].shape != "hat":
                        head.x = round(scene_pos.x() / GRID) * GRID
                        head.y = round(scene_pos.y() / GRID) * GRID
                    elif head is not None:
                        head.x = round(scene_pos.x() / GRID) * GRID
                        head.y = round(scene_pos.y() / GRID) * GRID
                    self.relayout_from(head_id)
            except ProgramError as exc:
                self.status_message.emit(str(exc))
                self.layout_all()
            self._clear_drag_state()
            self.program_changed.emit()
        self.viewport().update()
        event.accept()

    def _clear_drag_state(self) -> None:
        self._dragging = False
        self._drag_subtree = []
        self._drag_offsets.clear()
        for item in self.items.values():
            item.update()

    def _detach(self, head_id: str) -> None:
        for other in self.program.blocks.values():
            for attr in ("next", "then", "otherwise", "body"):
                if getattr(other, attr) == head_id:
                    setattr(other, attr, None)

    def _connect(self, head_id: str, target: Tuple[str, str]) -> None:
        """Wpina głowę w gniazdo; wypchnięty wcześniej stos dokleja do ogona."""
        parent_id, socket = target
        parent = self.program.get(parent_id)
        if parent is None:
            return
        attr = {"next": "next", "then": "then", "else": "otherwise",
                "body": "body"}[socket]
        displaced = getattr(parent, attr)
        self.program.set_socket(parent_id, socket, head_id)
        if displaced and displaced != head_id and displaced not in self._drag_subtree:
            tail = self.program.get(head_id)
            while tail is not None and tail.next:
                tail = self.program.get(tail.next)
            if tail is not None:
                try:
                    self.program.set_socket(tail.id, "next", displaced)
                except ProgramError:
                    pass  # najgorsze: wypchnięty stos zostanie sierotą
        self.relayout_from(parent_id if socket != "next" else head_id)
        self.layout_all()

    # ----------------------------------------------- usuwanie blokow
    def delete_selected(self) -> None:
        """Klawisz Delete — usuwa zaznaczone głowy wraz z podgrafami."""
        self._delete_blocks([bid for bid, it in self.items.items()
                             if it.isSelected()])

    def _delete_blocks(self, head_ids: Iterable[str]) -> None:
        start = self.program.start_block()
        start_id = start.id if start else None
        removed = False
        for bid in head_ids:
            if self.program.get(bid) is None:
                continue          # juz usuniety razem z nadzedcem
            if bid == start_id:
                self.status_message.emit(t("canvas.start_required"))
                continue
            self.program.remove_block(bid)
            removed = True
        if removed:
            # stan przeciągania/podświetlenia nie może wskazywać na trupa
            self._drag_head = None
            self._drag_subtree = []
            self._snap_target = None
            if self._active_block not in self.program.blocks:
                self._active_block = None
            self.refresh()
            self.program_changed.emit()
            self.block_selected.emit(None)

    def _has_parent(self, block_id: str) -> bool:
        return any(getattr(blk, attr) == block_id
                   for blk in self.program.blocks.values()
                   for attr in ("next", "then", "otherwise", "body"))

    def _show_context_menu(self, viewport_pos: QPoint) -> None:
        """Menu kontekstowe (PPM): usuń blok / odłącz od rodzica."""
        block_item = self._block_item(self.itemAt(viewport_pos))
        if block_item is None:
            return
        bid = block_item.block.id
        if not block_item.isSelected():
            self.scene.clearSelection()
            for member in self._subtree(bid):
                self.items[member].setSelected(True)
            self.block_selected.emit(bid)
        start = self.program.start_block()
        is_start = start is not None and start.id == bid
        count = len(self._subtree(bid))
        self.setFocus()
        menu = QMenu(self)
        act_delete = menu.addAction(
            t("canvas.menu.delete_many", n=count - 1) if count > 1
            else t("canvas.menu.delete_one"))
        act_delete.setEnabled(not is_start)
        act_detach = menu.addAction(t("canvas.menu.detach"))
        act_detach.setEnabled(not is_start and self._has_parent(bid))
        chosen = menu.exec(self.mapToGlobal(viewport_pos))
        if chosen is None:
            return
        # Akcje wykonujemy PO powrocie z menu.exec — NIGDY na stosie
        # dispatchu contextMenuEvent/mouseReleaseEvent, ktory trzyma surowe
        # wskazniki do itemow sceny. Zagniezdzone usuniecie elementow w tym
        # miejscu = use-after-free (0xC0000409).
        if chosen is act_delete:
            QTimer.singleShot(0, lambda: self._delete_blocks([bid]))
        elif chosen is act_detach:
            def _apply_detach() -> None:
                self._detach(bid)
                self.refresh()
                self.program_changed.emit()
            QTimer.singleShot(0, _apply_detach)

    # ------------------------------------------------- klawiatura
    def keyPressEvent(self, event) -> None:
        # Skladnia PySide6: Qt.Key.Key_Delete (plaski enum). Bledne
        # Qt.Key.Key.Delete rzuca AttributeError wewnatrz wirtualnej metody
        # wywolywanej z natywnej petli zdarzen — interpreter nie ma gdzie
        # propagowac wyjatku i proces wysypuje sie z kodem 0xC0000409.
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        super().keyPressEvent(event)

    # ----------------------------------------------- drag & drop z palety
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_BLOCK):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_BLOCK):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(self.MIME_BLOCK):
            super().dropEvent(event)
            return
        from ..core.model.blocks import BlockType
        type_name = bytes(event.mimeData().data(self.MIME_BLOCK)).decode()
        try:
            block_type = BlockType(type_name)
        except ValueError:
            return
        pos = self.mapToScene(event.position().toPoint())
        try:
            block = self.program.add_block(
                block_type, round(pos.x() / GRID) * GRID,
                round(pos.y() / GRID) * GRID)
        except ProgramError as exc:
            self.status_message.emit(str(exc))
            return
        self.refresh()
        self.items[block.id].setSelected(True)
        self.block_selected.emit(block.id)
        self.program_changed.emit()
        event.acceptProposedAction()
