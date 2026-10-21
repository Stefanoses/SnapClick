"""Smoke-testy GUI (sklada okna, reakcje paneli, runda canvas->model->plik).

Uwaga: na tej instalacji PySide6/Windows platforma 'offscreen' wywala
QApplication, wiec testy korzystaja z domyslnej platformy (Windows działa
headless bez okien dopóki ich nie show()). Jezeli brak wyswietlacza,
testy pomijaja sie (QApplication nie powstanie -> skip).
"""
from __future__ import annotations

import pytest

qapp = pytest.importorskip("PySide6.QtWidgets", reason="PySide6 wymagany")


@pytest.fixture(scope="module")
def qapp_instance():
    from PySide6.QtWidgets import QApplication
    try:
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # brak dostepnego QPA (np. CI bez ekranu)
        pytest.skip(f"QApplication niedostepny: {exc}")
    yield app


@pytest.fixture()
def main_window(qapp_instance, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # dane aplikacji (projects/, settings) trzymamy z dala od repo w testach
    from snapclick.core import paths as app_paths
    monkeypatch.setattr(app_paths, "app_dir", lambda: tmp_path)
    from snapclick.gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.storage.dirty = False   # close() nie pyta o zapis (modal na offscreen)
    win.close()


def test_window_builds(main_window):
    assert main_window.storage.program is not None
    assert main_window.canvas.items == {}
    assert main_window.btn_run.isEnabled()


def test_add_block_via_program_updates_canvas(main_window):
    from snapclick.core.model.blocks import BlockType
    block = main_window.storage.program.add_block(BlockType.START, 0, 0)
    main_window.canvas.refresh()
    assert block.id in main_window.canvas.items
    assert main_window.storage.dirty is True


def test_selection_populates_properties(main_window):
    from snapclick.core.model.blocks import BlockType
    block = main_window.storage.program.add_block(BlockType.CLICK, 10, 10)
    main_window.canvas.refresh()
    main_window._on_block_selected(block.id)
    # panel ma widgety dla parametrow bloku click
    assert main_window.properties._widgets

    # zmiana wartosci -> zapis do bloku
    main_window.properties._widgets["button"].set_value("right")
    main_window.properties._commit()
    assert block.params["button"] == "right"


def test_connect_snap_writes_graph(main_window):
    from snapclick.core.model.blocks import BlockType
    start = main_window.storage.program.add_block(BlockType.START, 0, 0)
    wait = main_window.storage.program.add_block(BlockType.WAIT, 300, 300)
    main_window.canvas.refresh()
    main_window.canvas._drag_head = wait.id
    main_window.canvas._snap_target = (start.id, "next")
    main_window.canvas._connect(wait.id, (start.id, "next"))
    assert start.next == wait.id
    main_window.canvas._drag_head = main_window.canvas._snap_target = None


def test_save_and_reload_roundtrip(main_window, tmp_path):
    from snapclick.core.model.blocks import BlockType
    start = main_window.storage.program.add_block(BlockType.START, 5, 5)
    wait = main_window.storage.program.add_block(BlockType.WAIT, 5, 60)
    main_window.storage.program.set_socket(start.id, "next", wait.id)
    path = tmp_path / "projekt.snapclick"
    main_window.storage.save(path)
    assert path.is_file()

    from snapclick.project.storage import ProjectStorage
    other = ProjectStorage()
    other.load(path)
    assert len(other.program.blocks) == 2
    reloaded_start = other.program.start_block()
    assert reloaded_start is not None and reloaded_start.next == wait.id


def test_legacy_m2proj_migrates_on_load(main_window, tmp_path):
    """Stary plik .m2proj otwiera sie i jest migrowany do .snapclick."""
    from snapclick.core.model.blocks import BlockType
    start = main_window.storage.program.add_block(BlockType.START, 5, 5)
    wait = main_window.storage.program.add_block(BlockType.WAIT, 5, 60)
    main_window.storage.program.set_socket(start.id, "next", wait.id)
    legacy = tmp_path / "stary.m2proj"
    main_window.storage.save(legacy)   # zapis pod stara nazwa (symulacja)
    assert legacy.is_file()

    from snapclick.project.storage import ProjectStorage
    other = ProjectStorage()
    other.load(legacy)
    assert len(other.program.blocks) == 2
    assert other.path == tmp_path / "stary.snapclick"
    assert not legacy.exists()   # plik przeniesiony (rename)


def test_validate_blocks_run_on_empty(main_window):
    problems = main_window.storage.program.validate()
    assert any("START" in p for p in problems)


def test_palette_chip_drag_starts_ok(main_window, monkeypatch):
    """Drag z palety nie moze wywalic wyjatku (regresja QDrag.setHotSpot)."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from snapclick.core.model.blocks import BLOCK_META, BlockType
    from snapclick.gui.palette import _BlockChip

    chip = _BlockChip(BLOCK_META[BlockType.CLICK])
    dropped = {}

    class FakeDrag:
        def __init__(self, source):
            pass

        def setMimeData(self, mime):
            dropped["mime"] = mime

        def setPixmap(self, pm):
            dropped["pixmap"] = pm

        def setHotSpot(self, point):
            assert isinstance(point, QPoint)
            dropped["hotspot"] = point

        def exec(self, action):
            dropped["exec"] = action

    monkeypatch.setattr("snapclick.gui.palette.QDrag", FakeDrag)

    def button_event(kind, x, y):
        return QMouseEvent(kind, QPointF(x, y), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    chip.mousePressEvent(button_event(QEvent.Type.MouseButtonPress, 5, 10))
    chip.mouseMoveEvent(button_event(QEvent.Type.MouseMove, 40, 30))

    assert "hotspot" in dropped and "exec" in dropped
    payload = bytes(dropped["mime"].data("application/x-m2-blocktype"))
    assert payload.decode() == "click"
    chip.deleteLater()


# ------------------------------------------------------------- usuwanie blokow
def test_canvas_focus_policy_is_strong(main_window):
    """QGraphicsView domyslnie nie przejmuje fokusu kliknieciem — bez
    StrongFocus klawisz Delete nigdy nie trafilby do keyPressEvent."""
    from PySide6.QtCore import Qt
    assert main_window.canvas.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_delete_selected_removes_block_and_cascades(main_window):
    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    wait = program.add_block(BlockType.WAIT, 0, 60)
    click = program.add_block(BlockType.CLICK, 0, 120)
    program.set_socket(start.id, "next", wait.id)
    program.set_socket(wait.id, "next", click.id)
    main_window.canvas.refresh()

    main_window.canvas.items[wait.id].setSelected(True)
    main_window.canvas.delete_selected()

    assert wait.id not in program.blocks
    assert click.id not in program.blocks      # podpiety stos tez usuniety
    assert start.id in program.blocks
    assert start.next is None
    assert wait.id not in main_window.canvas.items
    assert main_window.storage.dirty is True


def test_delete_selected_protects_start_block(main_window):
    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    main_window.canvas.refresh()

    messages = []
    main_window.canvas.status_message.connect(messages.append)
    main_window.canvas.items[start.id].setSelected(True)
    main_window.canvas.delete_selected()

    assert start.id in program.blocks
    assert any("START" in m for m in messages)


def test_delete_key_press_dispatches_without_crash(main_window):
    """Regresja 0xC0000409: klawisz Delete musi przejsc przez cala natywna
    sciezke (sendEvent -> keyPressEvent). Wczesniej bledna skladnia
    Qt.Key.Key.Delete rzucala AttributeError wewnatrz wirtualnej metody
    Shiboken i proces wysypial sie bez pythonowego tracebacka."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    iffy = program.add_block(BlockType.IF_FOUND, 0, 60)
    t1 = program.add_block(BlockType.CLICK, 0, 120)
    t2 = program.add_block(BlockType.WAIT, 0, 180)
    e1 = program.add_block(BlockType.WAIT, 0, 240)
    program.set_socket(start.id, "next", iffy.id)
    program.set_socket(iffy.id, "then", t1.id)
    program.set_socket(t1.id, "next", t2.id)
    program.set_socket(iffy.id, "else", e1.id)
    main_window.canvas.refresh()
    main_window.canvas.setFocus()
    for bid in main_window.canvas._subtree(iffy.id):
        main_window.canvas.items[bid].setSelected(True)

    for key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
        ev = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(main_window.canvas.viewport(), ev)

    # IF + caly podgraf usuniete, START zostal
    assert iffy.id not in program.blocks
    assert t1.id not in program.blocks and e1.id not in program.blocks
    assert start.id in program.blocks


def _make_if_stack(program):
    from snapclick.core.model.blocks import BlockType
    start = program.add_block(BlockType.START, 0, 0)
    iffy = program.add_block(BlockType.IF_FOUND, 0, 60)
    t1 = program.add_block(BlockType.CLICK, 0, 120)
    t2 = program.add_block(BlockType.WAIT, 0, 180)
    e1 = program.add_block(BlockType.WAIT, 0, 240)
    program.set_socket(start.id, "next", iffy.id)
    program.set_socket(iffy.id, "then", t1.id)
    program.set_socket(t1.id, "next", t2.id)
    program.set_socket(iffy.id, "else", e1.id)
    return start, iffy


def test_deleted_items_survive_current_dispatch(main_window):
    """Regresja 0xC0000409: usuniete BlockItem musza pozostac ZYWE dopoki
    trwa biezacy dispatch (Qt trima surowe wskazniki hover/press) i zostac
    zwolnione dopiero, gdy petla zdarzen 'oddycha'."""
    from PySide6.QtWidgets import QApplication

    start, iffy = _make_if_stack(main_window.storage.program)
    main_window.canvas.refresh()
    for bid in main_window.canvas._subtree(iffy.id):
        main_window.canvas.items[bid].setSelected(True)
    main_window.canvas.delete_selected()

    # usuniete itemy trzymane przy zyciu, a ich C++ jest dostepne
    assert len(main_window.canvas._dying) == 4
    for it in main_window.canvas._dying:
        assert it.block.id            # RuntimeError => C++ juz nie zyje

    QApplication.processEvents()      # brak popupu/przyciskow -> zwolnienie
    assert main_window.canvas._dying == []
    assert start.id in main_window.storage.program.blocks
    assert iffy.id not in main_window.storage.program.blocks


def test_dispose_never_touches_cpp_object_during_dispatch(main_window):
    """Regresja 0xC0000409 (przypadek 'Powtorz N razy' z >1 dzieckiem):
    _dispose_item NIE wolno wywolywac zadnych operacji na obiekcie C++
    (removeItem/setSelected) w trakcie biezacego dispatchu — item tylko
    znika wizualnie; realne usuniecie nastepuje w czystym tyku petli."""
    from PySide6.QtWidgets import QApplication

    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    rep = program.add_block(BlockType.REPEAT, 0, 60)
    c1 = program.add_block(BlockType.WAIT, 0, 120)
    c2 = program.add_block(BlockType.WAIT, 0, 180)
    c3 = program.add_block(BlockType.KEY_PRESS, 0, 240)
    program.set_socket(start.id, "next", rep.id)
    program.set_socket(rep.id, "body", c1.id)
    program.set_socket(c1.id, "next", c2.id)
    program.set_socket(c2.id, "next", c3.id)
    main_window.canvas.refresh()

    rep_item = main_window.canvas.items[rep.id]
    main_window.canvas._dispose_item(rep_item)
    # w trakcie dispatchu: obiekt C++ nietkniety (item wciaz w scenie,
    # ale niewidoczny i niezaznaczalny)
    assert rep_item.scene() is main_window.canvas.scene
    assert not rep_item.isVisible()
    assert not rep_item.isEnabled()
    QApplication.processEvents()          # czysty tyk -> realne usuniecie
    assert rep_item.scene() is None       # removeItem wykonane
    assert main_window.canvas._dying == []


def test_repeat_subtree_delete_with_multiple_children(main_window):
    """Regresja user-case: usuwanie rodzica 'Powtórz N razy' z 3 dziećmi."""
    from PySide6.QtWidgets import QApplication

    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    rep = program.add_block(BlockType.REPEAT, 0, 60)
    program.set_socket(start.id, "next", rep.id)
    head = None
    for i in range(3):
        blk = program.add_block(BlockType.WAIT, 0, 120 + 60 * i)
        if head is None:
            program.set_socket(rep.id, "body", blk.id)
            head = blk
        else:
            program.set_socket(head.id, "next", blk.id)
            head = blk
    main_window.canvas.refresh()
    for bid in main_window.canvas._subtree(rep.id):
        main_window.canvas.items[bid].setSelected(True)
    main_window.canvas.delete_selected()
    assert len(main_window.canvas._dying) == 4   # odlozone, C++ zyje
    for it in main_window.canvas._dying:
        assert it.block.id
    QApplication.processEvents()
    assert rep.id not in program.blocks
    assert start.id in program.blocks


def test_dying_items_wait_for_popup_to_close(main_window):
    """Przy otwartym popupie (menu kontekstowe = zagnieadzona petla zdarzen)
    zwolnienie musi byc przelozone az do jego zamkniecia."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMenu

    start, iffy = _make_if_stack(main_window.storage.program)
    main_window.canvas.refresh()
    menu = QMenu(main_window.canvas)
    menu.addAction("noop")
    menu.popup(main_window.canvas.mapToGlobal(QPoint(10, 10)))
    QApplication.processEvents()
    try:
        main_window.canvas._dispose_item(main_window.canvas.items[iffy.id])
        QTest.qWait(250)              # wielokrotnie wiecej niz interwal retry
        assert len(main_window.canvas._dying) == 1, "zwolniono przy popupie!"
        assert main_window.canvas._dying[0].block.id
    finally:
        menu.close()
        QApplication.processEvents()
    QTest.qWait(250)
    assert main_window.canvas._dying == []


def test_panels_have_no_hard_max_width(main_window):
    """Regresja responsive: panele w splitterze NIE moga miec gornego limitu
    szerokosci — dawniej setMaximumWidth obcinal ich zawartosc."""
    QWIDGETSIZE_MAX = 16777215   # Qt'owy brak limitu

    for widget, name in ((main_window.palette, "paleta"),
                         (main_window.properties, "właściwości"),
                         (main_window.templates, "szablony")):
        assert widget.maximumWidth() == QWIDGETSIZE_MAX, name
    assert main_window.canvas.minimumWidth() > 0


def test_splitter_layout_responsive(main_window):
    """Główny układ: poziomy splitter z 3 panelami + pionowy (canvas|log)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    horiz = main_window.findChildren(QSplitter)
    assert any(s.orientation() == Qt.Orientation.Horizontal for s in horiz)
    assert any(s.orientation() == Qt.Orientation.Vertical for s in horiz)
    for s in horiz:
        assert not s.childrenCollapsible()


def test_palette_chip_label_elides_when_narrow(main_window):
    """Wezki panel -> etykieta klocka skracana wielokropkiem, nie ucinana."""
    from snapclick.gui.palette import _BlockChip

    chips = main_window.palette.findChildren(_BlockChip)
    assert chips
    chip = chips[0]
    original = chip._label.text()
    chip.resize(60, 34)
    from PySide6.QtGui import QResizeEvent
    chip.resizeEvent(QResizeEvent(chip.size(), chip.size()))
    text = chip._label.text()
    assert text == original or text.endswith("…"), text


def test_theme_style_defined():
    from snapclick.gui import theme
    assert "QWidget" in theme.STYLE
    assert theme.BG.lower() in theme.STYLE.lower()
    # dark-mode: wypelnienie klocka CIEMNE (L ~84), ramka jaśniejsza ale
    # nie 'swiecaca' — tekst BLOCK_TEXT ma wtedy wysoki kontrast
    from snapclick.core.model.blocks import BLOCK_META
    for meta in BLOCK_META.values():
        fill = theme.block_fill(meta.color)
        _, _, l_fill, _ = fill.getHsl()
        _, _, l_border, _ = theme.block_border(fill).getHsl()
        assert l_fill <= 110
        assert l_border <= 190
        assert l_border > l_fill


def test_choice_combos_have_no_duplicates(main_window):
    """Regresja: listy choice nie moga zawierac duplikatow (dawniej
    'left'/'screen'/'stop' dublowaly sie, bo addItems nie ustawial
    userData, a set_value->findData(-1) doklejal wartosc na koniec).

    Od i18n: itemData = SUROWA wartosc (trafia do projektu), itemText =
    tlumaczona etykieta — dlatego porownujemy userData."""
    from PySide6.QtWidgets import QComboBox

    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    click = program.add_block(BlockType.CLICK, 0, 0)
    main_window.properties.set_block(click, lambda: [])

    for key, choices in (("button", ("left", "right", "middle")),
                         ("region", ("screen", "window", "custom")),
                         ("on_fail", ("stop", "continue"))):
        combo = main_window.properties._widgets[key].editor
        assert isinstance(combo, QComboBox)
        data = [combo.itemData(i) for i in range(combo.count())]
        assert data == list(choices), f"{key}: {data}"
        texts = [combo.itemText(i) for i in range(combo.count())]
        assert len(set(texts)) == len(texts), f"{key}: duplikaty etykiet"

    # przełaczenie bloku w tę samą wartość nie może nic duplikować
    main_window.properties.set_block(click, lambda: [])
    combo = main_window.properties._widgets["button"].editor
    assert [combo.itemData(i) for i in range(combo.count())] == ["left", "right", "middle"]


def test_properties_delete_button_removes_selected(main_window):
    from snapclick.core.model.blocks import BlockType
    program = main_window.storage.program
    start = program.add_block(BlockType.START, 0, 0)
    wait = program.add_block(BlockType.WAIT, 0, 60)
    main_window.canvas.refresh()

    assert not main_window.properties.btn_delete.isEnabled() 