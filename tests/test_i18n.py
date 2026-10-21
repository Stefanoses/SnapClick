"""Testy warstwy i18n: kompletnosc katalogow + przeaczanie jezyka na zywo."""
from __future__ import annotations

import pytest

from snapclick.i18n import CATALOGS, choice_label, get_lang, set_lang, t


@pytest.fixture(autouse=True)
def pl_lang():
    """Kazdy test modulu startuje i konczy w jezyku pl (bez zapisu preferencji).

    autouse: testy ponizej przechodza na EN w srodku — bez przywrocenia
    stanu wycieklyby do innych modulow i zmienily im komunikaty (regresja).
    """
    prev = get_lang()
    set_lang("pl", persist=False)
    yield
    set_lang(prev, persist=False)


# --------------------------------------------------------------- katalogi
def test_catalogs_have_identical_keys():
    """EN nie moze byc ubozszy oaden PL (i odwrotnie) — inaczej UI po cichu
    wroci do polskiego fallbacku dla brakujacych kluczy."""
    pl_keys, en_keys = set(CATALOGS["pl"]), set(CATALOGS["en"])
    assert pl_keys - en_keys == set(), f"brakuje w EN: {sorted(pl_keys - en_keys)}"
    assert en_keys - pl_keys == set(), f"brakuje w PL: {sorted(en_keys - pl_keys)}"


def test_catalogs_no_empty_values():
    for lang, cat in CATALOGS.items():
        for key, value in cat.items():
            assert value.strip(), f"{lang}/{key} jest pusty"


def test_t_formats_kwargs_and_falls_back():
    assert t("summary.image", value="buy_btn") in ("obraz: buy_btn",
                                                   "image: buy_btn")
    # nieznany klucz -> zwrot samego klucza (UI nigdy nie wywala)
    assert t("no.such.key.xyz") == "no.such.key.xyz"
    # zle kwargs nie moga wywrocic tlumaczenia
    assert t("summary.image")  # brak wymaganego pola -> surowy szablon


def test_choice_label_translates_known_and_passes_raw():
    assert choice_label("left") == "lewy"
    assert choice_label("screen") == "cały ekran"
    assert choice_label("right") == "prawy"
    # wartosci bez klucza (np. nazwa klawisza) przechodza surowa — tlumaczenie
    # nie moze zepsuc danych projektu
    assert choice_label("f1") == "f1"
    set_lang("en", persist=False)
    assert choice_label("left") == "left"
    assert choice_label("screen") == "whole screen"


def test_set_lang_persist_false_does_not_write(monkeypatch, tmp_path):
    """persist=False (sciezka testowa) nie wolno tworzyc pliku ustawien."""
    from snapclick.core import paths as app_paths

    monkeypatch.setattr(app_paths, "app_dir", lambda: tmp_path)
    set_lang("en" if get_lang() == "pl" else "pl", persist=False)
    assert not (tmp_path / "snapclick-data").exists()


# -------------------------------------------------- model + silnik po EN
def test_block_labels_follow_language():
    from snapclick.core.model.blocks import BLOCK_META, BlockType

    pl_label = BLOCK_META[BlockType.CLICK].label
    set_lang("en", persist=False)
    en_label = BLOCK_META[BlockType.CLICK].label
    assert pl_label != en_label
    assert en_label  # niepusta etykieta EN


def test_program_validate_problems_localized():
    from snapclick.core.model.blocks import BlockType
    from snapclick.core.model.program import Program

    program = Program()
    program.add_block(BlockType.WAIT)          # sierota = problem (soft)
    pl = program.validate()[0]
    set_lang("en", persist=False)
    en = program.validate()[0]
    assert pl != en
    assert en  # komunikat istnieje rowniez po angielsku


# ------------------------------------------------------------ GUI na zywo
@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_live_language_switch(qapp):
    from snapclick.gui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win.btn_run.text() == t("toolbar.run")
        assert "Uruchom" in win.btn_run.text()

        # przelaczenie na EN: menu, przyciski i kategorie palety musza
        # nadazyc natychmiast, bez restartu aplikacji
        set_lang("en", persist=False)
        assert "Run" in win.btn_run.text()
        assert win.menu_file.title() == "&File"
        assert win.right_tabs.tabText(
            win.right_tabs.indexOf(win.templates)) == "Templates"

        # paleta: kategorie + etykiety klockow po angielsku
        texts = [lbl.text() for lbl, _ in win.palette._cat_labels]
        assert "ACTIONS" in texts
        # chip bywa elidowany (offscreen) — sprawdzamy zrodlo etykiety: meta
        # renderowana przez i18n + odswiezony tekst chipa niepusty
        from snapclick.core.model.blocks import BLOCK_META, BlockType
        en_click = BLOCK_META[BlockType.CLICK].label
        assert en_click == "Click element"
        assert any(c.meta.type == BlockType.CLICK.value
                   and c.meta.label == en_click for c in win.palette._chips)
        assert all(c._label.text() for c in win.palette._chips)

        # panel wlasciwosci otwartego bloku CLICK: formularz odbudowany po EN
        from snapclick.core.model.blocks import BlockType
        program = win.storage.program
        click = program.add_block(BlockType.CLICK, 0, 0)
        win.properties.set_block(click, lambda: [])
        set_lang("pl", persist=False)
        assert win.properties._widgets["button"].editor.itemText(0) == "lewy"
        set_lang("en", persist=False)
        assert win.properties._widgets["button"].editor.itemText(0) == "left"
        # wartosc w projekcie (userData) niezmienna przy przeaczeniu jezyka
        assert win.properties._widgets["button"].editor.itemData(0) == "left"
    finally:
        win.storage.dirty = False   # close() nie pyta o zapis (modal offscreen)
        win.close()                 # odrejestrowuje słuchacza i18n
