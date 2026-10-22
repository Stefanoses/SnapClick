"""Interpreter drzewa bloków.

``Interpreter.run()`` wołany jest w wątku roboczym (patrz ``gui/runner.py``).
Nie dotyka Qt ani GUI — komunikuje się wyłącznie przez ``EventBus`` i
backendy platformowe (wstrzykiwane — w testach podstawiamy moki).
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

from ...i18n import t
from ..model.blocks import Block, BlockType
from ..model.program import Program
from ..platform.base import (
    BackendError,
    InputBackend,
    Region,
    ScreenBackend,
    WindowBackend,
)
from ..settings import get_settings
from ..vision.matcher import MatchResult, find_template
from ..vision.templates import TemplateRegistry
from .context import BlockFailed, RunContext
from .events import EngineEvent, EventBus, EventKind


class Interpreter:
    """Wykonuje ``Program`` na backendach platformowych."""

    def __init__(
        self,
        program: Program,
        templates: TemplateRegistry,
        screen: ScreenBackend,
        input_backend: InputBackend,
        windows: Optional[WindowBackend] = None,
        events: Optional[EventBus] = None,
    ) -> None:
        self.program = program
        self.templates = templates
        self.screen = screen
        self.input = input_backend
        self.windows = windows
        self.events = events or EventBus()
        # Nieistniejace indeksy monitorow zgłaszamy raz na przebieg, a nie
        # przy kazdym bloku (pesel w logu przy petli while).
        self._warned_monitors: set = set()

    # ------------------------------------------------------------------ API
    def run(self, context: Optional[RunContext] = None) -> str:
        """Uruchamia scenariusz. Zwraca status końcowy: ok | stopped | error."""
        ctx = context or RunContext()
        problems = self.program.validate()
        if problems:
            for p in problems:
                self.events.emit(EngineEvent(EventKind.ERROR, message=p))
            self.events.emit(EngineEvent(
                EventKind.RUN_FINISHED, message=t("engine.validation_errors"),
                data={"status": "error"}))
            return "error"

        start = self.program.start_block()
        assert start is not None  # validate() powyżej gwarantuje
        self.events.emit(EngineEvent(EventKind.RUN_STARTED,
                                     message=self.program.name))
        # Region okna cache'ujemy na start przebiegu (okno zwykle się nie rusza
        # w czasie akcji; zmiana tytułu = nowy przebieg). Awaria backendu okien
        # NIE moze wywrocic run() ponad ponizszy try/except — RUN_FINISHED musi
        # byc wyemitowany zawsze, inaczej GUI wisi na "Stopping…" (regresja
        # AttributeError('get_error_handler') na X11).
        if self.windows is not None and ctx.window_region is None:
            try:
                region = self.windows.find_region(self.program.window_title)
            except Exception as exc:  # pragma: no cover - backend bez okien
                region = None
                self.events.emit(EngineEvent(
                    EventKind.LOG,
                    message=t("engine.window_query_error", error=exc)))
            ctx.window_region = region
            if region is None and self.program.window_title:
                self.events.emit(EngineEvent(
                    EventKind.LOG,
                    message=t("engine.window_not_found",
                              title=self.program.window_title)))
        # Tablica monitorow cache'ujemy na starcie (identycznie jak region
        # okna) — backend ekranu nie musi byc wywolywany przy kazdym bloku.
        if not ctx.monitors:
            list_monitors = getattr(self.screen, "monitors", None)
            if callable(list_monitors):
                try:
                    for m in list_monitors():
                        ctx.monitors[int(m.index)] = tuple(m.region)
                except Exception:  # pragma: no cover - backend bez enumeracji
                    pass
        # Pulpit wirtualny moze zaczynac sie w ujemnych wspolrzednych (monitor
        # po lewej/na gorze) — zrzut 'region=None' startuje w tym rogu, wiec
        # przesuniecie wyniku liczymy od niego, a nie od (0, 0).
        if ctx.virtual_origin == (0, 0):
            vb = getattr(self.screen, "virtual_bounds", None)
            if callable(vb):
                try:
                    bounds = vb()
                    ctx.virtual_origin = (int(bounds[0]), int(bounds[1]))
                except Exception:  # pragma: no cover - backend bez bounds
                    pass
        # Klikanie metodą PostMessage wymaga uchwytu okna — przekazujemy go
        # warstwie wejścia, gdy backend udostępnia taką metodę (Win32).
        set_target = getattr(self.input, "set_target_window", None)
        find_hwnd = getattr(self.windows, "find_hwnd", None)
        if callable(set_target) and callable(find_hwnd):
            try:
                set_target(find_hwnd(self.program.window_title))
            except Exception:  # pragma: no cover - backend bez okien
                pass
        # Focus: gry DirectX/WebGL ignorują mysz, gdy okno nie jest
        # aktywne — przywołujemy je na wierzch RAZ przed pierwszym kliknięciem.
        # Wyjątek z aktywacji NIE może wywracać całego przebiegu.
        if (self.windows is not None and self.program.window_title
                and get_settings().focus_enabled):
            try:
                focused = self.windows.activate(self.program.window_title)
            except Exception as exc:
                focused = False
                self.events.emit(EngineEvent(
                    EventKind.LOG,
                    message=t("engine.focus_error", error=exc)))
            self.events.emit(EngineEvent(
                EventKind.LOG,
                message=t("engine.focus_ok" if focused else "engine.focus_fail",
                          title=self.program.window_title)))
        try:
            self._run_stack(start.id, ctx, depth=0)
            status = "stopped" if ctx.stopped else "ok"
        except BlockFailed as exc:
            status = "error"
            self.events.emit(EngineEvent(EventKind.ERROR, message=str(exc)))
        except BackendError as exc:
            status = "error"
            self.events.emit(EngineEvent(EventKind.ERROR, message=str(exc)))
        except Exception as exc:  # pragma: no cover - zabezpieczenie wątku
            status = "error"
            self.events.emit(EngineEvent(
                EventKind.ERROR, message=t("engine.unexpected", exc=repr(exc))))
        self.events.emit(EngineEvent(
            EventKind.RUN_FINISHED, message=f"status={status}",
            data={"status": status, "completed": ctx.completed_blocks}))
        return status

    # -------------------------------------------------------- przejście
    _MAX_DEPTH = 256  # bezpiecznik przed rekurencją przez zagnieżdżone pętle

    def _run_stack(self, head_id: str, ctx: RunContext, depth: int) -> None:
        """Wykonuje stos bloków zaczynając od ``head_id`` (aż next=None)."""
        current: Optional[str] = head_id
        while current:
            if ctx.stopped:
                return
            if depth > self._MAX_DEPTH:
                raise BlockFailed(t("engine.max_depth"))
            block = self.program.get(current)
            if block is None:
                return
            ctx.completed_blocks += 1
            self.events.emit(EngineEvent(
                EventKind.BLOCK_STARTED, block_id=block.id,
                message=block.type, data={"label": self._label(block)}))
            next_id = self._execute(block, ctx, depth)
            self.events.emit(EngineEvent(
                EventKind.BLOCK_FINISHED, block_id=block.id, message=block.type))
            current = next_id

    def _label(self, block: Block) -> str:
        from ..model.blocks import BLOCK_META
        meta = BLOCK_META.get(block.type)
        return meta.label if meta else block.type

    # --------------------------------------------------------- dystrybucja
    def _execute(self, block: Block, ctx: RunContext, depth: int) -> Optional[str]:
        btype = block.type
        if btype == BlockType.START.value:
            return block.next
        if btype == BlockType.CLICK.value:
            self._do_click(block, ctx)
            return block.next
        if btype == BlockType.TYPE_TEXT.value:
            self._do_type_text(block, ctx)
            return block.next
        if btype == BlockType.WAIT.value:
            seconds = float(block.param("seconds") or 0.0)
            interrupted = ctx.sleep(seconds)
            return None if interrupted else block.next
        if btype == BlockType.KEY_PRESS.value:
            combo = str(block.param("combo") or "")
            self.events.emit(EngineEvent(
                EventKind.ACTION, block_id=block.id,
                message=t("engine.keys", combo=combo)))
            self.input.press_combo(combo)
            return block.next
        if btype == BlockType.IF_FOUND.value:
            match = self._search(block, ctx)
            branch = block.then if match else block.otherwise
            if branch:
                self._run_stack(branch, ctx, depth + 1)
            return block.next
        if btype == BlockType.WHILE_FOUND.value:
            self._do_while(block, ctx, depth)
            return block.next
        if btype == BlockType.REPEAT.value:
            count = int(block.param("count") or 0)
            for i in range(count):
                if ctx.stopped:
                    return None
                if block.body:
                    self._run_stack(block.body, ctx, depth + 1)
                if i < count - 1 and ctx.sleep(0.0):  # tylko kontrola stop
                    return None
            return block.next
        raise BlockFailed(t("engine.unhandled_block", block_type=btype))

    # -------------------------------------------------------------- akcje
    def _do_click(self, block: Block, ctx: RunContext) -> None:
        match = self._search(block, ctx)
        if match is None:
            on_fail = str(block.param("on_fail") or "stop")
            template_id = str(block.param("template") or "?")
            if on_fail == "stop":
                raise BlockFailed(t("engine.not_found_stop",
                                    template=template_id))
            self.events.emit(EngineEvent(
                EventKind.LOG, block_id=block.id,
                message=t("engine.skip_click", template=template_id)))
            return
        dx = int(block.param("offset_x") or 0)
        dy = int(block.param("offset_y") or 0)
        point = match.center_with_offset(dx, dy)
        button = str(block.param("button") or "left")
        double = bool(block.param("double"))
        self._maybe_focus(block)
        self.events.emit(EngineEvent(
            EventKind.ACTION, block_id=block.id,
            message=t("engine.click", button=button, dbl=" x2" if double else "",
                      point=point, score=match.score),
            data={"point": point}))
        self.input.click(point[0], point[1], button=button, double=double)
        self.events.emit(EngineEvent(
            EventKind.FOUND, block_id=block.id,
            data={"center": point, "score": match.score}))
        post = float(block.param("post_wait") or 0.0)
        if post > 0:
            ctx.sleep(post)

    def _maybe_focus(self, block: Block) -> None:
        """Reaktywacja okna przed kliknięciem (gdy wymaga tego scenariusz).

        Parametr bloku ``focus``: auto (reguła globalna) / on (zawsze) /
        off (nigdy). Reguła globalna ``focus_after_click`` służy grom, które
        tracą focus w trakcie gry (np. po dialogu systemowym).
        """
        if self.windows is None or not self.program.window_title:
            return
        mode = str(block.param("focus") or "auto")
        if mode == "off":
            return
        if mode == "auto" and not get_settings().focus_after_click:
            return
        try:
            self.windows.activate(self.program.window_title)
        except Exception:
            pass  # focus to ułatwienie, nie warunek konieczny kliknięcia

    def _do_type_text(self, block: Block, ctx: RunContext) -> None:
        text = str(block.param("text") or "")
        method = str(block.param("method") or "auto")
        self.events.emit(EngineEvent(
            EventKind.ACTION, block_id=block.id,
            message=t("engine.type_text", method=method, text=text[:40])))
        self.input.type_text(text, method=method)
        post = float(block.param("post_wait") or 0.0)
        if post > 0:
            ctx.sleep(post)

    def _do_while(self, block: Block, ctx: RunContext, depth: int) -> None:
        max_iter = int(block.param("max_iterations") or 100)
        delay = float(block.param("iteration_delay") or 0.0)
        iterations = 0
        while not ctx.stopped:
            match = self._search(block, ctx, emit_found=False)
            if match is None:
                break
            iterations += 1
            self.events.emit(EngineEvent(
                EventKind.FOUND, block_id=block.id,
                message=t("engine.iteration", n=iterations),
                data={"center": match.center, "score": match.score}))
            if block.body:
                self._run_stack(block.body, ctx, depth + 1)
            if ctx.stopped:
                break
            if iterations >= max_iter:
                self.events.emit(EngineEvent(
                    EventKind.LOG, block_id=block.id,
                    message=t("engine.while_limit", n=max_iter)))
                break
            if delay > 0 and ctx.sleep(delay):
                break

    # ------------------------------------------------------------ szukanie
    def _search(self, block: Block, ctx: RunContext,
                emit_found: bool = True) -> Optional[MatchResult]:
        """Szuka szablonu bloku z timeoutem i pollingiem; reaguje na STOP."""
        template_id = str(block.param("template") or "")
        template = self.templates.get(template_id)  # BackendError gdy brak
        threshold = float(block.param("threshold") or 0.9)
        timeout = float(block.param("timeout") or 0.0)
        poll = float(block.param("poll") or 0.15)
        region = self._resolve_region(block, ctx)

        import time
        deadline = time.monotonic() + timeout
        while True:
            if ctx.stopped:
                return None
            frame = self.screen.grab(region)
            # Gdy przeszukujemy region, wynik zwracany jest w jego układzie —
            # przeliczamy na współrzędne ekranu przez offset regionu.
            match = find_template(frame, template, threshold=threshold)
            if match is not None:
                # Przeliczenie na wspolrzedne ekranu: region -> jego rog;
                # caly pulpit -> jego lewy-gorny rog (MOZE BYC UJEMNY, gdy
                # monitor siega na lewo/ponad glowny — stary kod zalozył
                # (0,0) i klikial o |origin| pikseli obok celu).
                rx, ry = (region[0], region[1]) if region is not None \
                    else ctx.virtual_origin
                match = MatchResult(
                    center=(match.center[0] + rx, match.center[1] + ry),
                    top_left=(match.top_left[0] + rx, match.top_left[1] + ry),
                    score=match.score, size=match.size)
                ctx.last_match_center = match.center
                if emit_found:
                    self.events.emit(EngineEvent(
                        EventKind.FOUND, block_id=block.id,
                        data={"center": match.center, "score": match.score}))
                return match
            if time.monotonic() >= deadline:
                self.events.emit(EngineEvent(
                    EventKind.NOT_FOUND, block_id=block.id,
                    message=t("engine.not_found", template=template_id,
                              threshold=threshold, timeout=timeout),
                    data={"template": template_id}))
                return None
            if ctx.sleep(poll):
                return None

    def _monitor_region(self, block: Block,
                        ctx: RunContext) -> Optional[Region]:
        """Region dla regionu 'screen' z uwzglednieniem wyboru monitora.

        Priorytet: wlasny parametr 'monitor' bloku (null = dziedzicz) ->
        'monitor' programu -> caly pulpit wirtualny (region=None).
        """
        idx = self.program.monitor
        raw = block.param("monitor")
        if raw is not None and raw != "":
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                idx = self.program.monitor
        if not idx:            # None albo 0 -> jawnie caly pulpit
            return None
        region = ctx.monitors.get(idx)
        if region is None:
            if idx not in self._warned_monitors:
                self._warned_monitors.add(idx)
                self.events.emit(EngineEvent(
                    EventKind.LOG, block_id=block.id,
                    message=t("engine.monitor_missing", idx=idx)))
            return None        # awaryjnie: szukanie po calym pulpicie
        return region

    def _resolve_region(self, block: Block,
                        ctx: RunContext) -> Optional[Region]:
        kind = str(block.param("region") or "screen")
        if kind == "screen":
            return self._monitor_region(block, ctx)
        if kind == "window":
            if self.windows is not None:
                title = str(block.param("window_title")
                            or self.program.window_title or "")
                if title:
                    region = self.windows.find_region(title)
                    if region is not None:
                        return region
            return ctx.window_region
        if kind == "custom":
            raw = str(block.param("custom_region") or "")
            try:
                x, y, w, h = (int(float(p)) for p in raw.replace(";", ",").split(","))
                if w > 0 and h > 0:
                    return (x, y, w, h)
            except ValueError:
                pass
            self.events.emit(EngineEvent(
                EventKind.LOG, block_id=block.id,
                message=t("engine.bad_region", raw=raw)))
        return None
