"""Globalny motyw wizualny aplikacji (ciemna, stonowana szarosc).

Cel: praca wieczorna bez bolu oczu — srednio ciemne tlo (nie czern),
obnizona saturacja i kontrast, ale zachowana czytelnosc. Jedno zrodlo prawdy
dla kolorow: stale ponizej + STYLE (QSS) nakladany na QApplication.

Kolory blokow (BLOCK_META) pozostaja 'archiwalne' (projekt plikowy!), wiec
dla renderowania GUI przechodza przez block_fill() — desaturacja i
dopasowanie do ciemnego kontekstu. Serializacja projektu ich nie dotyka.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

# ------------------------------------------------------------------ paleta
BG          = "#262A31"   # tlo okna
BG_PANEL    = "#2E333B"   # panele, karty, listy
BG_INPUT    = "#21252B"   # pola edycji, canvas, log
BG_HOVER    = "#363C46"   # tlo elementu pod kursorem
BG_PRESSED  = "#1B1E23"   # tlo przycisku wcisnietego
BORDER      = "#424852"   # delikatne obwodki
BORDER_SOFT = "#353B44"
TEXT        = "#D7DBE1"   # tekst podstawowy (zlamana biel)
TEXT_MUTED  = "#98A0AC"   # tekst drugoplanowy
TEXT_FAINT  = "#6E7682"

ACCENT      = "#5B87C9"   # stonowany niebieski (focus/zaznaczenie)
ACCENT_OK   = "#3E9E6B"   # 'Uruchom'
ACCENT_STOP = "#C25660"   # 'STOP' / usuwanie (sciszona czerwien)
ACCENT_MARK = "#3ECF8E"   # znacznik znalezionego elementu na canvasie

SCENE_BG    = "#1E2227"   # tlo canvasu (ciemniejsze od okna, bez czerni)

# Typografia na klockach — wysoki kontrast na CIEMNYM wypelnieniu
BLOCK_TEXT     = "#EDF1F6"   # etykieta klocka (zloma biel)
BLOCK_TEXT_DIM = "#C6CFDA"   # podsumowanie parametrow


def block_fill(color: int | str, factor: float = 1.0) -> QColor:
    """Adaptuje kolor typu bloku do ciemnego UI.

    Kolory projektowe sa ' Scratch-owo' jasne i nasycone — na ciemnym tle
    mecza oczy. Sciagamy saturacje i górn granice jasnosci, zachowujac
    rozpoznawalnosc kategorii.
    """
    c = QColor(color) if isinstance(color, str) else QColor.fromRgb(color)
    h, s, l, _ = c.getHsl()
    s = max(90, min(s, 160))
    lum = 84 if factor >= 1.0 else int(84 * factor)
    c.setHsl(h, s, lum, 255)
    return c


def block_border(fill: QColor) -> QColor:
    """Kolorowa ramka — główny identyfikator kategorii klocka (dark mode)."""
    h, s, _, _ = fill.getHsl()
    c = QColor()
    c.setHsl(h, min(s + 26, 255), 148)
    return c


def block_accent(fill: QColor) -> QColor:
    """Najjasniejszy odcien kategorii (kropka w palecie, akcenty)."""
    h, s, _, _ = fill.getHsl()
    c = QColor()
    c.setHsl(h, min(s + 40, 255), 168)
    return c


# ---------------------------------------------------------------------- QSS
STYLE = f"""
/* ---- bazy ---------------------------------------------------------- */
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{
    background: {BG_PANEL}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 6px;
}}

/* ---- menu / statusbar ---------------------------------------------- */
QMenuBar {{ background: {BG_PANEL}; border-bottom: 1px solid {BORDER_SOFT}; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {BG_HOVER}; }}
QMenu {{
    background: {BG_PANEL}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG_HOVER}; }}
QMenu::item:disabled {{ color: {TEXT_FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 4px 8px; }}
QStatusBar {{ background: {BG_PANEL}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER_SOFT}; }}
QStatusBar::item {{ border: none; }}

/* ---- przyciski ------------------------------------------------------ */
QPushButton {{
    background: {BG_HOVER}; color: {TEXT};
    border: 1px solid {BORDER_SOFT}; border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton:hover {{ background: {BORDER_SOFT}; }}
QPushButton:pressed {{ background: {BG_PRESSED}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: {BG_PANEL}; }}
QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 4px; }}
QToolButton:hover {{ background: {BG_HOVER}; }}

/* ---- pola formularzy ------------------------------------------------ */
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {BORDER_SOFT}; border-radius: 5px;
    padding: 4px 6px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_FAINT}; background: {BG_PANEL};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {BG_HOVER}; border: none; width: 16px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {BORDER_SOFT};
}}

/* ---- combo ---------------------------------------------------------- */
QComboBox {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {BORDER_SOFT}; border-radius: 5px;
    padding: 4px 8px;
}}
QComboBox:hover {{ border: 1px solid {BORDER}; }}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_PANEL}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px;
    selection-background-color: {BG_HOVER};
    outline: none;
}}

/* ---- checkbox -------------------------------------------------------- */
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---- karty / grupy --------------------------------------------------- */
QGroupBox {{
    border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    margin-top: 10px; padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px;
    padding: 0 4px; color: {TEXT_MUTED};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    top: -1px; background: {BG_PANEL};
}}
QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED};
    padding: 7px 14px; border: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {BG_HOVER}; color: {TEXT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* ---- listy ------------------------------------------------------------ */
QListWidget, QListView {{
    background: {BG_INPUT}; border: 1px solid {BORDER_SOFT};
    border-radius: 6px; padding: 4px; outline: none;
}}
QListWidget::item, QListView::item {{
    padding: 6px; border-radius: 4px;
}}
QListWidget::item:hover, QListView::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{ background: {ACCENT}; color: #FFFFFF; }}

/* ---- scrollbary -------------------------------------------------------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SOFT}; border-radius: 4px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {BORDER}; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_SOFT}; border-radius: 4px; min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {BORDER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0; background: none; border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---- splinery ------------------------------------------------------------ */
QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:horizontal {{ width: 5px; }}
QSplitter::handle:vertical {{ height: 5px; }}
QSplitter::handle:hover {{ background: {BORDER_SOFT}; }}

/* ---- napisy pomocnicze ---------------------------------------------------- */
QLabel {{ background: transparent; }}
"""
