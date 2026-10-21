"""Project file: JSON ``.snapclick`` + ``assets/`` folder with PNG templates.

The project folder is kept separate from the code — the user copies the
project file together with its ``assets/`` folder as a scenario backup.

Legacy ``.m2proj`` files are still readable; opening one migrates it in
place to the new ``.snapclick`` extension (the format is identical).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..core.model.program import Program
from ..core.model.serializer import load_program_dict, program_to_dict
from ..core.vision.templates import TemplateRegistry
from ..i18n import t


class StorageError(RuntimeError):
    """Błąd odczytu/zapisu projektu."""


class ProjectStorage:
    """A single open project in memory + disk operations."""

    PROJECT_EXT = ".snapclick"
    LEGACY_EXT = ".m2proj"
    ASSETS_DIRNAME = "assets"

    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.program = Program()
        self.registry: Optional[TemplateRegistry] = None
        self.dirty = False

    # ------------------------------------------------------------------ API
    def new_project(self, directory: Path, name: Optional[str] = None) -> Path:
        if name is None:
            name = t("project.new_default")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{self._safe_name(name)}{self.PROJECT_EXT}"
        self.program = Program(name=name)
        self.registry = TemplateRegistry(directory / self.ASSETS_DIRNAME)
        self.registry.set_templates([])
        self.dirty = True
        return self.path

    def save(self, path: Optional[Path] = None) -> Path:
        if self.registry is None:
            raise StorageError(t("storage.not_open"))
        target = Path(path) if path else self.path
        if target is None:
            raise StorageError(t("storage.no_path"))
        target.parent.mkdir(parents=True, exist_ok=True)
        data = program_to_dict(self.program, self.registry.entries())
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(target)  # zapis atomowy
        self.path = target
        self.dirty = False
        return target

    def load(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            raise StorageError(t("storage.no_file", path=path))
        # Legacy .m2proj files are renamed in place to .snapclick (same
        # format); from here on we work with the migrated path.
        path = self._migrate_legacy(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError(
                t("storage.bad_json", name=path.name, exc=exc)) from exc
        try:
            program, templates = load_program_dict(data)
        except ValueError as exc:
            raise StorageError(str(exc)) from exc
        registry = TemplateRegistry(path.parent / self.ASSETS_DIRNAME)
        try:
            registry.set_templates(templates)
        except Exception as exc:
            # Dozwolone: szablon usunięty z dysku — blok zgłosi błąd przy RUN,
            # ale projekt powinien się otworzyć. Rejestrujemy co da się wczytać.
            usable = []
            for entry in templates:
                try:
                    TemplateRegistry(registry.assets_dir).set_templates([entry])
                    usable.append(entry)
                except Exception:  # noqa: PERF203 - lista zwykle mała
                    continue
            registry.set_templates(usable)
            self._load_warning = t("storage.template_load_warn", exc=exc)
        else:
            self._load_warning = None
        self.program = program
        self.registry = registry
        self.path = path
        self.dirty = False

    @property
    def load_warning(self) -> Optional[str]:
        return getattr(self, "_load_warning", None)

    def save_as(self, path: Path) -> Path:
        """Zapis do nowej lokalizacji + kopiowanie szablonów przy zmianie katalogu."""
        assert self.registry is not None
        entries = self.registry.entries()
        old_assets = self.path.parent / self.ASSETS_DIRNAME if self.path else None
        target = self.save(path)
        new_assets = target.parent / self.ASSETS_DIRNAME
        if old_assets is not None and old_assets != new_assets and old_assets.is_dir():
            import shutil
            shutil.copytree(old_assets, new_assets, dirs_exist_ok=True)
        self.registry = TemplateRegistry(new_assets)
        self.registry.set_templates(entries)
        return target

    # ---------------------------------------------------------------- util
    @staticmethod
    def _migrate_legacy(path: Path) -> Path:
        """Rename a legacy ``.m2proj`` file to ``.snapclick`` (same format).

        Returns the path to use afterwards. If the rename is impossible
        (read-only media, name clash) we keep loading the old path.
        """
        if path.suffix != ProjectStorage.LEGACY_EXT:
            return path
        new_path = path.with_suffix(ProjectStorage.PROJECT_EXT)
        if new_path.exists():
            return path
        try:
            path.rename(new_path)
        except OSError:
            return path
        return new_path

    @staticmethod
    def _safe_name(name: str) -> str:
        keep = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name)
        return keep.strip() or "projekt"
