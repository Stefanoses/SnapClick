"""Warstwa GUI (PySide6): edytor blokowy, podgląd, uruchamianie scenariuszy.

Moduły:
    canvas          -- canvas bloczków (QGraphicsView, snapowanie gniazd)
    palette         -- paleta bloków do przeciągania
    properties      -- panel właściwości wybranego bloku
    templates_panel -- zarządzanie szablonami PNG
    capture         -- narzędzie przechwycenia wycinka ekranu
    runner          -- sterowanie uruchomieniem silnika w wątku + hotkey
    main_window     -- kompozycja całości
    app             -- punkt wejścia QApplication
"""
