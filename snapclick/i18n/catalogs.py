"""Katalogi tlumaczen: polski (domyślny) i angielski.

Zasady:
  * klucze grupowane prefiksami: block./param./choice./prog./validate./engine./
    runner./storage./tpl./detect./app./toolbar./status./tab./log./menu./act./
    dlg./err./confirm./msg./palette./props./canvas./capture./tpl_panel./
    tpl_dlg./tpl_file./language.
  * wartości z miejscami ``{name}`` są formatowane przez ``i18n.t()``
    (str.format) — cokolwiek tu jest, musi byc poprawnym kluczem formatu;
  * testy spozniają oba słowniki pod względem zbioru kluców
    (test_i18n.test_catalogs_parity), więc EN nie może nic zgubić.
"""
from __future__ import annotations

from typing import Dict

# ------------------------------------------------------------------ polski
PL: Dict[str, str] = {
    # --- nazwy języków (stałe w obu katalogach)
    "language.pl": "Polski",
    "language.en": "English",

    # --- kategorie bloków
    "cat.events": "Zdarzenia",
    "cat.actions": "Akcje",
    "cat.logic": "Logika",

    # --- etykiety bloków
    "block.start.label": "Kiedy uruchomisz",
    "block.click.label": "Kliknij element",
    "block.type_text.label": "Wpisz tekst",
    "block.wait.label": "Czekaj",
    "block.key_press.label": "Naciśnij klawisz",
    "block.if_found.label": "Jeżeli element znaleziony",
    "block.while_found.label": "Powtarzaj dopóki element obecny",
    "block.repeat.label": "Powtórz N razy",

    # --- etykiety parametrow
    "param.template": "Szablon (obraz)",
    "param.button": "Przycisk",
    "param.double": "Podwójne kliknięcie",
    "param.offset_x": "Przesunięcie X",
    "param.offset_y": "Przesunięcie Y",
    "param.threshold": "Próg podobieństwa",
    "param.timeout": "Timeout szukania [s]",
    "param.poll": "Częstotliwość szukania [s]",
    "param.region": "Obszar szukania",
    "param.window_title": "Tytuł okna (gdy region=window)",
    "param.monitor": "Monitor (gdy region=screen)",
    "props.window_title_hint": "fragment tytułu okna aplikacji docelowej",
    "param.custom_region": "Region x,y,w,h (gdy region=custom)",
    "param.post_wait_click": "Czekaj po kliknięciu [s]",
    "param.focus": "Aktywuj okno przed kliknięciem",
    "param.on_fail": "Przy braku elementu",
    "param.text": "Tekst",
    "param.method": "Metoda",
    "param.post_wait_type": "Czekaj po wpisaniu [s]",
    "param.seconds": "Sekund",
    "param.combo": "Klawisze (np. ctrl+v, esc)",
    "param.max_iterations": "Limit iteracji (bezpiecznik)",
    "param.iteration_delay": "Przerwa między iteracjami [s]",
    "param.count": "Liczba powtórzeń",

    # --- wartosci choice (dane projektu zostaja angielskie)
    "choice.left": "lewy",
    "choice.right": "prawy",
    "choice.middle": "środkowy",
    "choice.screen": "cały ekran",
    "choice.window": "okno",
    "choice.custom": "własny",
    "choice.stop": "zatrzymaj",
    "choice.continue": "kontynuuj",
    "choice.auto": "auto",
    "choice.on": "zawsze",
    "choice.off": "nigdy",
    "choice.type": "wpisywanie",
    "choice.clipboard": "schowek",
    "choice.postmessage": "PostMessage (WM_CHAR)",

    # --- podsumowanie na klocku
    "summary.image": "obraz: {value}",
    "summary.right": "ppm",
    "summary.middle": "śpm",

    # --- bledy grafu (Program)
    "prog.start_only_one": "Program może zawierać tylko jeden blok START.",
    "prog.dup_id": "Zduplikowane ID bloku: {block_id}",
    "prog.self_connect": "Blok nie może być podłączony sam do siebie.",
    "prog.no_src": "Brak bloku źródłowego: {block_id}",
    "prog.no_socket": "Blok {block_type} nie ma gniazda '{socket}'.",
    "prog.no_dst": "Brak bloku docelowego: {block_id}",
    "prog.cycle": "Cykl w grafie bloków jest niedozwolony.",

    # --- walidacja
    "validate.no_start": "Brak bloku START ('{label}').",
    "validate.unknown_type": "Blok {block_id}: nieznany typ '{block_type}'.",
    "validate.no_socket": "Blok {label} ({block_id}) nie posiada gniazda '{socket}'.",
    "validate.dangling": "Blok {block_id} wskazuje na nieistniejący '{child}'.",
    "validate.multi_parent": "Blok {child} wpięty w wiele gniazd: {sockets}.",
    "validate.cycle_detected": "Wykryto cykl przechodzący przez blok {block_id}.",
    "validate.orphan": "Blok {label} ({block_id}) nie jest podłączony do żadnego "
                       "stosu (nie zostanie wykonany).",

    # --- silnik (interpreter)
    "engine.validation_errors": "błędy walidacji",
    "engine.window_not_found": "Nie znaleziono okna '{title}' — regiony "
                               "'window' będą szukać na całym ekranie.",
    "engine.window_query_error": "Błąd listowania okien: {error} — szukam bez "
                                 "regionu okna.",
    "engine.focus_ok": "Okno '{title}' uaktywnione (focus).",
    "engine.focus_fail": "Nie udało się uaktywnić okna '{title}' — kliknięcia "
                         "mogą nie trafiać do gry.",
    "engine.focus_error": "Błąd aktywacji okna: {error} — kontynuuję bez focusu.",
    "engine.unexpected": "Nieoczekiwany błąd: {exc}",
    "engine.max_depth": "Przekroczono dozwolone zagnieżdżenie bloków.",
    "engine.keys": "klawisze: {combo}",
    "engine.unhandled_block": "Nieobsłużony typ bloku: {block_type}",
    "engine.not_found_stop": "Nie znaleziono elementu '{template}' — scenariusz "
                             "zatrzymany (zmień 'Przy braku elementu' na "
                             "'kontynuuj').",
    "engine.skip_click": "Element '{template}' nie znaleziony — pomijam klik.",
    "engine.click": "klik {button}{dbl} w {point} (score={score:.2f})",
    "engine.type_text": "wpisz ({method}): {text!r}",
    "engine.clipboard_unavailable": "Schowek niedostępny (brak xclip/xsel) — "
                                    "wpisuję klawiszami (XTEST).",
    "engine.iteration": "iteracja {n}",
    "engine.while_limit": "Limit {n} iteracji osiągnięty — bezpiecznik pętli WHILE.",
    "engine.not_found": "Brak elementu '{template}' "
                        "(próg {threshold:.2f}, timeout {timeout:.1f}s)",
    "engine.bad_region": "Nieprawidłowy region '{raw}' — używam całego ekranu.",
    "engine.monitor_missing": "Monitor {idx} nie istnieje w obecnej konfiguracji "
                              "— szukam po całym pulpicie.",

    # --- runner
    "runner.already_running": "Scenariusz już się wykonuje.",
    "runner.thread_error": "Wątek silnika: {exc}",

    # --- storage / projekty
    "storage.not_open": "Projekt nie jest otwarty.",
    "storage.no_path": "Nie podano ścieżki zapisu.",
    "storage.no_file": "Plik projektu nie istnieje: {path}",
    "storage.bad_json": "Uszkodzony JSON w {name}: {exc}",
    "storage.template_load_warn": "Niektórych szablonów nie udało się wczytać: {exc}",
    "project.new_default": "Nowy scenariusz",
    "project.shop_default": "Mój scenariusz",
    "project.unsaved": "niezapisany",

    # --- rejestr szablonow
    "tpl.bad_id": "Nieprawidłowe ID szablonu {tpl_id!r} — dozwolone małe "
                  "litery, cyfry, '-' i '_' (max 64 znaki).",
    "tpl.missing_file": "Szablon '{tpl_id}': brak pliku {path}",
    "tpl.load_fail": "Nie można wczytać obrazu: {path}",
    "tpl.not_in_project": "Szablon '{tpl_id}' nie istnieje w projekcie. "
                          "Dodaj go przez panel Szablony.",
    "tpl.encode_fail": "Nie udało się zakodować szablonu do PNG.",

    # --- backendy / platforma
    "detect.wayland": "Wykryto sesję Wayland. Bot wymaga sesji X11 (Xorg) — "
                      "wybierz na ekranie logowania sesję 'X11 / Xorg' lub "
                      "uruchom aplikację przez xwayland z ustawionym DISPLAY.",
    "detect.no_display": "Brak zmiennej DISPLAY — bot na Linuksie wymaga "
                         "działającego serwera X11.",
    "detect.unsupported": "Niewspierane środowisko: OS={os_name}, "
                          "sesja={session}. Bot działa na Windows 11 oraz "
                          "Linux z sesją X11.",

    # --- okno glowne / UI
    "app.title": "SnapClick — wizualny edytor automatyzacji",
    "app.title_doc": "SnapClick — {name} [{path}]{mark}",
    "toolbar.run": "▶  Uruchom (F5)",
    "toolbar.stop": "■  STOP (F10)",
    "toolbar.monitor": "Monitor:",
    "toolbar.monitor_tip": "Domyślny ekran dla wyszukiwania (gdy blok ma "
                           "region=Ekran). Pojedyncze bloki mogą go nadpisać "
                           "w polu „Monitor”.",
    "toolbar.layout_tip": "Pokaż układ monitorów (dwuklik na ekranie ustawia "
                          "go jako domyślny).",
    "layout.title": "Układ monitorów",
    "layout.hint": "Dwuklik na ekranie ustawia go jako domyślny monitor "
                   "wyszukiwania. ★ = monitor główny.",
    "layout.all": "Wszystkie ekrany",
    "layout.close": "Zamknij",
    "log.monitor_set": "Monitor domyślny: {what}.",
    "status.ready": "Gotowy",
    "status.running": "Wykonuję… (F10 = STOP)",
    "status.stopping": "Zatrzymywanie…",
    "status.ok": "Zakończono",
    "status.stopped": "Zatrzymano",
    "status.error": "Błąd",
    "tab.properties": "Właściwości",
    "tab.templates": "Szablony",
    "log.placeholder": "Log wykonania…",

    # --- menu i akcje
    "menu.file": "&Plik",
    "menu.run": "&Uruchom",
    "menu.language": "J&ęzyk",
    "act.new": "Nowy projekt…",
    "act.open": "&Otwórz projekt…",
    "act.save": "&Zapisz",
    "act.saveas": "Zapisz &jako…",
    "act.quit": "&Wyjście",
    "act.run": "&Uruchom",
    "act.stop": "&STOP",
    "act.settings": "&Ustawienia wejścia…",

    # --- dialog ustawien wejścia
    "dlg.settings_title": "Ustawienia wejścia i focusu",
    "dlg.settings_hint": "Jeśli gra nie reaguje na kliknięcia: zwiększ "
                         "przytrzymanie przycisku i czas osadzenia kursora.",
    "dlg.settings_mouse": "Mysz",
    "dlg.settings_focus": "Focus okna",
    "dlg.settings_method": "Metoda klikania",
    "choice.method_sendinput": "SendInput (DirectInput/OpenGL)",
    "choice.method_postmessage": "PostMessage (do HWND okna — omija antybot)",
    "choice.method_clipboard": "Schowek + Ctrl+V (pewne dla gier pod Wine/Proton)",
    "set.click_method": "Wysyłanie kliknięć",
    "set.type_method": "Wysyłanie tekstu",
    "set.click_method_hint": "Kliknięcia i tekst sterowane są osobno. "
                             "SendInput czyta DirectInput; PostMessage omija "
                             "filtry antybotów (LLMHF/LLKHF_INJECTED), ale "
                             "wymaga tytułu okna gry w programie. Gra "
                             "uruchomiona jako administrator wymaga też "
                             "uruchomienia tego programu z prawami admina.",
    "set.mouse_hold": "Przytrzymanie przycisku",
    "set.move_settle": "Osadzenie kursora przed kliknięciem",
    "set.double_gap": "Odstęp w dwukliku",
    "set.release_settle": "Po puszczeniu przycisku",
    "set.key_hold": "Przytrzymanie klawisza",
    "set.mod_settle": "Odstęp przy modyfikatorach (AltGr/Shift)",
    "set.focus_enabled": "Aktywuj okno gry przed startem scenariusza",
    "set.focus_after_click": "Aktywuj okno przed każdym kliknięciem (wolniejsze)",
    "set.focus_delay": "Czekaj po aktywacji okna",

    # --- komunikaty okna glownego
    "dlg.select_dir": "Wybierz katalog dla nowego projektu",
    "dlg.new_project": "Nowy projekt",
    "dlg.scenario_name": "Nazwa scenariusza:",
    "dlg.save_as": "Zapisz projekt jako",
    "file.filter": "Projekty SnapClick (*.snapclick *.m2proj)",
    "err.error": "Błąd",
    "err.open": "Błąd otwarcia",
    "err.save": "Błąd zapisu",
    "err.no_backend": "Brak backendu",
    "err.backend_unavailable": "Backend niedostępny.",
    "err.start": "Błąd startu",
    "confirm.discard_title": "Niezapisane zmiany",
    "confirm.discard_text": "Projekt ma niezapisane zmiany.\n"
                            "Zapisać przed kontynuacją?",
    "msg.incomplete": "Scenariusz niekompletny",
    "msg.incomplete_body": "Popraw najpierw:",
    "msg.warnings": "Ostrzeżenia",
    "msg.warnings_body": "Wykryto problemy:",
    "msg.continue": "\n\nKontynuować?",
    "log.platform": "Platforma: {os_name}/{session}",
    "log.warning": "Uwaga: {message}",
    "log.monitor_reset": "Monitor {idx} zniknął — przywrócono wszystkie ekrany.",
    "log.monitors_changed": "Wykryto zmianę konfiguracji ekranów — lista "
                            "monitorów odświeżona.",
    "log.created": "Utworzono projekt: {path}",
    "log.opened": "Otworzono: {path}",
    "log.saved": "Zapisano: {path}",
    "log.template_added": "Dodano szablon: {id}",

    # --- paleta
    "palette.title": "Klocki",

    # --- panel wlasciwosci
    "props.placeholder": "Zaznacz klocek na canvasie, aby edytować jego "
                         "właściwości.",
    "props.delete": "🗑  Usuń blok",
    "props.delete_tip": "Usuwa zaznaczony klocek wraz z podpiętymi pod nim.\n"
                        "Tożsame z klawiszem Delete na canvasie.",
    "props.no_params": "Ten klocek nie ma parametrów.",
    "props.parameters": "Parametry",
    "props.no_template": "(brak — dodaj w panelu Szablony)",
    "props.monitor_inherit": "jak program (pasek Monitor)",
    "props.monitor_all": "wszystkie ekrany (pulpit)",
    "props.monitor_item": "Monitor {idx} · {label}",
    "props.monitor_primary": "(główny)",

    # --- canvas
    "canvas.else_label": "W INNYM PRZYPADKU",
    "canvas.start_required": "Blok START jest wymagany — nie można go usunąć.",
    "canvas.menu.delete_many": "Usuń blok (ten i {n} podpiętych)",
    "canvas.menu.delete_one": "Usuń blok",
    "canvas.menu.detach": "Odłącz od rodzica",

    # --- przechwytywanie ekranu
    "capture.title": "Przechwyć obraz szablonu",
    "capture.info": "1. Przygotuj okno gry (element ma być widoczny).\n"
                    "2. Kliknij『Zrób zrzut i zaznacz』— ekran zamarznie.\n"
                    "3. Zaznacz myszą fragment interfejsu (np. przycisk『Kup』).",
    "capture.btn": "Zrób zrzut i zaznacz",
    "capture.monitor": "Ekran:",
    "capture.hiding": "Ukrywam okna aplikacji i robię zrzut…",
    "capture.grab_error": "Błąd zrzutu ekranu: {exc}",
    "capture.outside": "Zaznaczony obszar jest poza zrzutem.",
    "capture.save_error": "Błąd zapisu szablonu: {exc}",
    "capture.saved": "Zapisano szablon '{id}' ({w}×{h}).",
    "capture.overlay_hint": "Przeciągnij myszą, aby zaznaczyć obszar szablonu "
                            "(Esc = anuluj)",

    # --- panel szablonow
    "tpl_panel.title": "Szablony (wycinki interfejsu)",
    "tpl_panel.capture": "Przechwyć z ekranu…",
    "tpl_panel.file": "Z pliku PNG…",
    "tpl_panel.remove": "Usuń",
    "tpl_panel.hint": "Wskazówka: przechwytuj małe, charakterystyczne "
                      "fragmenty (napis na przycisku, ikonę).",
    "tpl_dlg.title": "Nowy szablon",
    "tpl_dlg.name": "Nazwa szablonu:",
    "tpl_dlg.placeholder": "np. kup_przycisk (małe litery, cyfry, - _)",
    "tpl_dlg.bad_name": "Nieprawidłowa nazwa",
    "tpl_file.title": "Wybierz obraz szablonu",
    "tpl_file.filter": "Obrazy (*.png *.jpg *.jpeg *.bmp);;Wszystkie pliki (*)",
    "tpl.remove_title": "Usuń szablon",
    "tpl.remove_body": "Usunąć szablon '{id}'?\nBloki się do niego odwołujące\n"
                       "zgłoszą błąd podczas RUN.",
}

# ------------------------------------------------------------------ angielski
EN: Dict[str, str] = {
    "language.pl": "Polski",
    "language.en": "English",

    "cat.events": "Events",
    "cat.actions": "Actions",
    "cat.logic": "Logic",

    "block.start.label": "When you run",
    "block.click.label": "Click element",
    "block.type_text.label": "Type text",
    "block.wait.label": "Wait",
    "block.key_press.label": "Press key",
    "block.if_found.label": "If element is found",
    "block.while_found.label": "Repeat while element present",
    "block.repeat.label": "Repeat N times",

    "param.template": "Template (image)",
    "param.button": "Button",
    "param.double": "Double click",
    "param.offset_x": "Offset X",
    "param.offset_y": "Offset Y",
    "param.threshold": "Similarity threshold",
    "param.timeout": "Search timeout [s]",
    "param.poll": "Search interval [s]",
    "param.region": "Search region",
    "param.window_title": "Window title (when region=window)",
    "param.monitor": "Monitor (when region=screen)",
    "props.window_title_hint": "part of the target window's title",
    "param.custom_region": "Region x,y,w,h (when region=custom)",
    "param.post_wait_click": "Wait after click [s]",
    "param.focus": "Activate window before click",
    "param.on_fail": "When element missing",
    "param.text": "Text",
    "param.method": "Method",
    "param.post_wait_type": "Wait after typing [s]",
    "param.seconds": "Seconds",
    "param.combo": "Keys (e.g. ctrl+v, esc)",
    "param.max_iterations": "Iteration limit (safety)",
    "param.iteration_delay": "Delay between iterations [s]",
    "param.count": "Repeat count",

    "choice.left": "left",
    "choice.right": "right",
    "choice.middle": "middle",
    "choice.screen": "whole screen",
    "choice.window": "window",
    "choice.custom": "custom",
    "choice.stop": "stop",
    "choice.continue": "continue",
    "choice.auto": "auto",
    "choice.on": "always",
    "choice.off": "never",
    "choice.type": "typing",
    "choice.clipboard": "clipboard",
    "choice.postmessage": "PostMessage (WM_CHAR)",

    "summary.image": "image: {value}",
    "summary.right": "RMB",
    "summary.middle": "MMB",

    "prog.start_only_one": "The program may contain only one START block.",
    "prog.dup_id": "Duplicate block ID: {block_id}",
    "prog.self_connect": "A block cannot be connected to itself.",
    "prog.no_src": "Missing source block: {block_id}",
    "prog.no_socket": "Block {block_type} has no socket '{socket}'.",
    "prog.no_dst": "Missing target block: {block_id}",
    "prog.cycle": "A cycle in the block graph is not allowed.",

    "validate.no_start": "Missing START block ('{label}').",
    "validate.unknown_type": "Block {block_id}: unknown type '{block_type}'.",
    "validate.no_socket": "Block {label} ({block_id}) has no socket '{socket}'.",
    "validate.dangling": "Block {block_id} points at missing block '{child}'.",
    "validate.multi_parent": "Block {child} plugged into multiple sockets: "
                             "{sockets}.",
    "validate.cycle_detected": "Detected a cycle through block {block_id}.",
    "validate.orphan": "Block {label} ({block_id}) is not connected to any "
                       "stack (it will not run).",

    "engine.validation_errors": "validation errors",
    "engine.window_not_found": "Window '{title}' not found — 'window' regions "
                               "will search the whole screen.",
    "engine.window_query_error": "Window listing error: {error} — searching "
                                 "without a window region.",
    "engine.focus_ok": "Window '{title}' activated (focus).",
    "engine.focus_fail": "Could not activate window '{title}' — clicks may "
                         "miss the game.",
    "engine.focus_error": "Window activation error: {error} — continuing "
                          "without focus.",
    "engine.unexpected": "Unexpected error: {exc}",
    "engine.max_depth": "Maximum block nesting depth exceeded.",
    "engine.keys": "keys: {combo}",
    "engine.unhandled_block": "Unhandled block type: {block_type}",
    "engine.not_found_stop": "Element '{template}' not found — scenario "
                             "stopped (change 'When element missing' to "
                             "'continue').",
    "engine.skip_click": "Element '{template}' not found — skipping click.",
    "engine.click": "click {button}{dbl} at {point} (score={score:.2f})",
    "engine.type_text": "type ({method}): {text!r}",
    "engine.clipboard_unavailable": "Clipboard unavailable (no xclip/xsel) — "
                                    "typing via keys (XTEST).",
    "engine.iteration": "iteration {n}",
    "engine.while_limit": "WHILE loop safety limit of {n} iterations reached.",
    "engine.not_found": "Element '{template}' not found "
                        "(threshold {threshold:.2f}, timeout {timeout:.1f}s)",
    "engine.bad_region": "Invalid region '{raw}' — using the whole screen.",
    "engine.monitor_missing": "Monitor {idx} does not exist in the current "
                              "setup — searching the whole desktop.",

    "runner.already_running": "A scenario is already running.",
    "runner.thread_error": "Engine thread: {exc}",

    "storage.not_open": "No project is open.",
    "storage.no_path": "No save path given.",
    "storage.no_file": "Project file does not exist: {path}",
    "storage.bad_json": "Corrupted JSON in {name}: {exc}",
    "storage.template_load_warn": "Some templates could not be loaded: {exc}",
    "project.new_default": "New scenario",
    "project.shop_default": "My first scenario",
    "project.unsaved": "unsaved",

    "tpl.bad_id": "Invalid template ID {tpl_id!r} — allowed lowercase "
                  "letters, digits, '-' and '_' (max 64 chars).",
    "tpl.missing_file": "Template '{tpl_id}': missing file {path}",
    "tpl.load_fail": "Cannot load image: {path}",
    "tpl.not_in_project": "Template '{tpl_id}' does not exist in the project. "
                          "Add it via the Templates panel.",
    "tpl.encode_fail": "Failed to encode template to PNG.",

    "detect.wayland": "Wayland session detected. The bot requires an X11 "
                      "(Xorg) session — choose 'X11 / Xorg' at the login "
                      "screen or run the app via xwayland with DISPLAY set.",
    "detect.no_display": "DISPLAY variable missing — the bot on Linux "
                         "requires a running X11 server.",
    "detect.unsupported": "Unsupported environment: OS={os_name}, "
                          "session={session}. The bot works on Windows 11 "
                          "and Linux with an X11 session.",

    "app.title": "SnapClick — visual automation editor",
    "app.title_doc": "SnapClick — {name} [{path}]{mark}",
    "toolbar.run": "▶  Run (F5)",
    "toolbar.stop": "■  STOP (F10)",
    "toolbar.monitor": "Monitor:",
    "toolbar.monitor_tip": "Default screen for finding (when a block uses "
                           "region=Screen). Individual blocks can override it "
                           "in the „Monitor” field.",
    "toolbar.layout_tip": "Show the monitor layout (double-click a screen to "
                          "make it the default).",
    "layout.title": "Monitor layout",
    "layout.hint": "Double-click a screen to make it the default search "
                   "monitor. ★ = primary monitor.",
    "layout.all": "All screens",
    "layout.close": "Close",
    "log.monitor_set": "Default monitor: {what}.",
    "status.ready": "Ready",
    "status.running": "Running… (F10 = STOP)",
    "status.stopping": "Stopping…",
    "status.ok": "Finished",
    "status.stopped": "Stopped",
    "status.error": "Error",
    "tab.properties": "Properties",
    "tab.templates": "Templates",
    "log.placeholder": "Execution log…",

    "menu.file": "&File",
    "menu.run": "&Run",
    "menu.language": "&Language",
    "act.new": "New project…",
    "act.open": "&Open project…",
    "act.save": "&Save",
    "act.saveas": "Save &as…",
    "act.quit": "&Exit",
    "act.run": "&Run",
    "act.stop": "&STOP",
    "act.settings": "Input &Settings…",

    "dlg.settings_title": "Input & focus settings",
    "dlg.settings_hint": "If the game ignores clicks: increase the button hold "
                         "and cursor settle time.",
    "dlg.settings_mouse": "Mouse",
    "dlg.settings_focus": "Window focus",
    "dlg.settings_method": "Click method",
    "choice.method_sendinput": "SendInput (DirectInput/OpenGL)",
    "choice.method_postmessage": "PostMessage (to window HWND — bypasses antybot)",
    "choice.method_clipboard": "Clipboard + Ctrl+V (reliable for Wine/Proton games)",
    "set.click_method": "Click delivery",
    "set.type_method": "Text delivery",
    "set.click_method_hint": "Clicks and text are controlled separately. "
                             "SendInput is read by DirectInput; PostMessage "
                             "bypasses antybot filters (LLMHF/LLKHF_INJECTED) "
                             "but requires the game window title in the "
                             "program settings. A game running as admin "
                             "requires this app to run as admin too.",
    "set.mouse_hold": "Button hold",
    "set.move_settle": "Cursor settle before click",
    "set.double_gap": "Double-click gap",
    "set.release_settle": "After button release",
    "set.key_hold": "Key hold",
    "set.mod_settle": "Modifier settle time (AltGr/Shift)",
    "set.focus_enabled": "Activate game window before scenario starts",
    "set.focus_after_click": "Activate window before every click (slower)",
    "set.focus_delay": "Wait after window activation",

    "dlg.select_dir": "Choose a directory for the new project",
    "dlg.new_project": "New project",
    "dlg.scenario_name": "Scenario name:",
    "dlg.save_as": "Save project as",
    "file.filter": "SnapClick projects (*.snapclick *.m2proj)",
    "err.error": "Error",
    "err.open": "Open error",
    "err.save": "Save error",
    "err.no_backend": "No backend",
    "err.backend_unavailable": "Backend unavailable.",
    "err.start": "Start error",
    "confirm.discard_title": "Unsaved changes",
    "confirm.discard_text": "The project has unsaved changes.\n"
                            "Save before continuing?",
    "msg.incomplete": "Incomplete scenario",
    "msg.incomplete_body": "Fix these first:",
    "msg.warnings": "Warnings",
    "msg.warnings_body": "Issues detected:",
    "msg.continue": "\n\nContinue?",
    "log.platform": "Platform: {os_name}/{session}",
    "log.warning": "Warning: {message}",
    "log.monitor_reset": "Monitor {idx} disappeared — reverted to all screens.",
    "log.monitors_changed": "Screen configuration changed — monitor list "
                            "refreshed.",
    "log.created": "Project created: {path}",
    "log.opened": "Opened: {path}",
    "log.saved": "Saved: {path}",
    "log.template_added": "Template added: {id}",

    "palette.title": "Blocks",

    "props.placeholder": "Select a block on the canvas to edit its properties.",
    "props.delete": "🗑  Delete block",
    "props.delete_tip": "Deletes the selected block together with everything "
                        "attached below it.\nSame as the Delete key on the canvas.",
    "props.no_params": "This block has no parameters.",
    "props.parameters": "Parameters",
    "props.no_template": "(none — add one in the Templates panel)",
    "props.monitor_inherit": "as program (Monitor bar)",
    "props.monitor_all": "all screens (desktop)",
    "props.monitor_item": "Monitor {idx} · {label}",
    "props.monitor_primary": "(primary)",

    "canvas.else_label": "OTHERWISE",
    "canvas.start_required": "The START block is required — it cannot be deleted.",
    "canvas.menu.delete_many": "Delete block (this one and {n} attached)",
    "canvas.menu.delete_one": "Delete block",
    "canvas.menu.detach": "Detach from parent",

    "capture.title": "Capture template image",
    "capture.info": "1. Prepare the game window (the element must be visible).\n"
                    "2. Click 'Take screenshot and select' — the screen freezes.\n"
                    "3. Select an interface fragment with the mouse (e.g. the "
                    "'Buy' button).",
    "capture.btn": "Take screenshot and select",
    "capture.monitor": "Screen:",
    "capture.hiding": "Hiding app windows and taking a screenshot…",
    "capture.grab_error": "Screenshot error: {exc}",
    "capture.outside": "The selected area is outside the screenshot.",
    "capture.save_error": "Template save error: {exc}",
    "capture.saved": "Saved template '{id}' ({w}×{h}).",
    "capture.overlay_hint": "Drag with the mouse to select the template area "
                            "(Esc = cancel)",

    "tpl_panel.title": "Templates (interface snippets)",
    "tpl_panel.capture": "Capture from screen…",
    "tpl_panel.file": "From PNG file…",
    "tpl_panel.remove": "Remove",
    "tpl_panel.hint": "Tip: capture small, distinctive fragments (button "
                      "text, an icon).",
    "tpl_dlg.title": "New template",
    "tpl_dlg.name": "Template name:",
    "tpl_dlg.placeholder": "e.g. buy_button (lowercase, digits, - _)",
    "tpl_dlg.bad_name": "Invalid name",
    "tpl_file.title": "Choose a template image",
    "tpl_file.filter": "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)",
    "tpl.remove_title": "Remove template",
    "tpl.remove_body": "Remove template '{id}'?\nBlocks referencing it will "
                       "report\nan error on RUN.",
}

CATALOGS: Dict[str, Dict[str, str]] = {"pl": PL, "en": EN}
