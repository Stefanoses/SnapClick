"""Rejestr szablonów PNG (wycinków interfejsu).

Szablony mieszkają w katalogu ``assets/`` obok pliku projektu.
Pliorytetowo traktujemy kanał alfa (maska) — wczytujemy jako ``IMREAD_UNCHANGED``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from ...i18n import t
from ..platform.base import BackendError

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


@dataclass(frozen=True)
class TemplateMeta:
    id: str
    file_name: str  # ścieżka względna katalogu assets/
    width: int
    height: int
    has_alpha: bool


class TemplateRegistry:
    """Trzyma metadane + cache tablic szablonów; wątkowo-odporny odczyt."""

    def __init__(self, assets_dir: Path) -> None:
        self.assets_dir = Path(assets_dir)
        self._meta: Dict[str, TemplateMeta] = {}
        self._cache: Dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------ odczyt
    @staticmethod
    def validate_id(t_id: str) -> str:
        if not _ID_RE.match(t_id):
            raise BackendError(t("tpl.bad_id", tpl_id=t_id))
        return t_id

    def set_templates(self, entries: List[dict]) -> None:
        """Ustawia listę zdefiniowaną przez projekt: [{id, file}, ...]."""
        self._meta.clear()
        self._cache.clear()
        for entry in entries:
            t_id = self.validate_id(str(entry["id"]))
            file_name = str(entry["file"])
            path = self.assets_dir / file_name
            if not path.is_file():
                raise BackendError(t("tpl.missing_file", tpl_id=t_id, path=path))
            img = self._load(path)
            h, w = img.shape[:2]
            self._meta[t_id] = TemplateMeta(
                id=t_id,
                file_name=file_name,
                width=w,
                height=h,
                has_alpha=img.ndim == 3 and img.shape[2] == 4,
            )
            self._cache[t_id] = img

    def _load(self, path: Path) -> np.ndarray:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise BackendError(t("tpl.load_fail", path=path))
        return img

    # ------------------------------------------------------------------ API
    @property
    def ids(self) -> List[str]:
        return sorted(self._meta)

    def meta(self, t_id: str) -> Optional[TemplateMeta]:
        return self._meta.get(t_id)

    def get(self, t_id: str) -> np.ndarray:
        img = self._cache.get(t_id)
        if img is None:
            raise BackendError(t("tpl.not_in_project", tpl_id=t_id))
        return img

    def add_from_array(self, t_id: str, image: np.ndarray) -> TemplateMeta:
        """Zapisuje przechwycony wycinek jako PNG i rejestruje go."""
        t_id = self.validate_id(t_id)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{t_id}.png"
        path = self.assets_dir / file_name
        ok, buf = cv2.imencode(".png", image)
        if not ok:
            raise BackendError(t("tpl.encode_fail"))
        path.write_bytes(buf.tobytes())
        loaded = self._load(path)
        h, w = loaded.shape[:2]
        meta = TemplateMeta(
            id=t_id, file_name=file_name, width=w, height=h,
            has_alpha=loaded.ndim == 3 and loaded.shape[2] == 4,
        )
        self._meta[t_id] = meta
        self._cache[t_id] = loaded
        return meta

    def remove(self, t_id: str, delete_file: bool = True) -> None:
        meta = self._meta.pop(t_id, None)
        self._cache.pop(t_id, None)
        if meta is not None and delete_file:
            path = self.assets_dir / meta.file_name
            try:
                path.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - plik otwarty w innej aplikacji
                pass

    def entries(self) -> List[dict]:
        """Lista do serializacji projektu."""
        return [{"id": m.id, "file": m.file_name} for m in
                sorted(self._meta.values(), key=lambda m: m.id)]
